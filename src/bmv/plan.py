import re
import sys
import traceback

from copy import deepcopy
from dataclasses import asdict, replace as clone
from itertools import groupby
from os.path import commonprefix
from pathlib import Path

from .constants import CON, STRUCTURES

from .problems import (
    CONTROLS,
    PROBLEM_NAMES as PN,
    PROBLEM_FORMATS as PF,
    Problem,
)

from .data_objects import (
    BmvError,
    RenamePair,
)

class RenamingPlan:

    DEFAULT_FILE_SYS_VAL = True

    def __init__(self,
                 # Path inputs and their structure.
                 inputs,
                 structure = None,
                 # User code for renaming and filtering.
                 rename_code = None,
                 filter_code = None,
                 indent = 4,
                 # Sequence numbering.
                 seq_start = 1,
                 seq_step = 1,
                 # File system via dependency injection.
                 file_sys = None,
                 # Problem controls.
                 skip = None,
                 clobber = None,
                 create = None,
                 ):

        # Basic attributes passed as arguments into the constructor.
        self.inputs = tuple(inputs)
        self.structure = structure or STRUCTURES.flat
        self.rename_code = rename_code
        self.filter_code = filter_code
        self.indent = indent
        self.seq_start = seq_start
        self.seq_step = seq_step
        self.file_sys = self.initialize_file_sys(file_sys)

        # Convert the problem-control inputs (skip, clobber, create) into
        # validated tuples of problem names controlled by each mechanism.
        self.skip = self.validated_pnames(CONTROLS.skip, skip)
        self.clobber = self.validated_pnames(CONTROLS.clobber, clobber)
        self.create = self.validated_pnames(CONTROLS.create, create)

        # From those validated problem-control tuples, build a lookup mapping
        # each Problem name to the user's requested control mechanism.
        self.control_lookup = self.build_control_lookup()

        # Problems that occur during the prepare() phase are stored in a dict.
        # A problem can be either controlled (as requested by the user) or not.
        # The dict maps each control mechanism to the problems that were
        # controlled by that mechanism. If the dict ends up having any
        # uncontrolled problems (under the None key), the RenamingPlan will
        # have failed.
        self.problems = {
            c : []
            for c in CONTROLS.keys()
        }
        self.problems[None] = []

        # The paths to be renamed will be stored as RenamePair instances.
        self.rps = tuple()

        # Lenth of the longest common prefix string on the original paths.
        self.prefix_len = 0

        self.filter_func = None
        self.rename_func = None

        self.has_prepared = False
        self.has_renamed = False
        self.new_groups = None

    ####
    #
    # Preparation before renaming.
    #
    # This method perform various validations and computations needed before
    # renaming can occur. The method does not raise; rather, when problems
    # occur, they are stored in self.problems based whether/how the user
    # has configured the plan to control them.
    #
    ####

    def prepare(self):
        # Don't prepare more than once.
        if self.has_prepared:
            return
        else:
            self.has_prepared = True

        # Get the input paths and parse them to get RenamePair instances.
        self.rps = self.parse_inputs()
        if self.failed:
            return

        # Create the renaming and filtering functions from
        # user-supplied code, if any was given.
        self.rename_func = self.make_user_defined_func('rename')
        self.filter_func = self.make_user_defined_func('filter')
        if self.failed:
            return

        # Run various steps that process the RenamePair instances individually:
        # filtering, computing new paths, or validating.
        #
        # We use the processed_rps() method to execute the step, handle
        # problems appropriately, and yield a potentially filtered collection
        # of potentially modified RenamePair instances.
        #
        rp_steps = (
            (None, self.execute_user_filter),
            (None, self.execute_user_rename),
            (None, self.check_orig_exists),
            (None, self.check_orig_new_differ),
            (None, self.check_new_not_exists),
            (None, self.check_new_parent_exists),
            (self.prepare_new_groups, self.check_new_collisions),
        )
        for prep_step, step in rp_steps:
            # Run any needed preparations and then the step.
            if prep_step:
                prep_step()
            self.rps = tuple(self.processed_rps(step))

            # Register problem if the step filtered out everything.
            if not self.rps:
                p = Problem(PN.all_filtered)
                self.handle_problem(p)

            # Stop if the plan has failed either directly or via filtering.
            if self.failed:
                return

    ####
    # Parsing inputs to obtain the original and, in some cases, new paths.
    ####

    def parse_inputs(self):

        def do_fail(name, *xs):
            p = Problem(name, *xs)
            self.handle_problem(p)
            return ()

        # If we have rename_code, inputs are just original paths.
        if self.rename_code:
            rps = tuple(
                RenamePair(orig, None)
                for orig in self.inputs
                if orig
            )
            if rps:
                return rps
            else:
                return do_fail(PN.parsing_no_paths)

        # Otherwise, organize inputs into original paths and new paths.
        if self.structure == STRUCTURES.paragraphs:
            # Paragraphs: first original paths, then new paths.
            groups = [
                list(lines)
                for g, lines in groupby(self.inputs, key = bool)
                if g
            ]
            if len(groups) == 2:
                origs, news = groups
            else:
                return do_fail(PN.parsing_paragraphs)

        elif self.structure == STRUCTURES.pairs:
            # Pairs: original path, new path, original path, etc.
            origs = []
            news = []
            current = origs
            for line in self.inputs:
                if line:
                    current.append(line)
                    current = news if current is origs else origs
        elif self.structure == STRUCTURES.rows:
            # Rows: original-new path pairs, as tab-delimited rows.
            origs = []
            news = []
            for row in self.inputs:
                if row:
                    cells = list(filter(None, row.split(CON.tab)))
                    if len(cells) == 2:
                        origs.append(cells[0])
                        news.append(cells[1])
                    else:
                        return do_fail(PN.parsing_row, row)

        else:
            # Flat: like paragraphs without the blank-line delimiter.
            paths = [line for line in self.inputs if line]
            i = len(paths) // 2
            origs, news = (paths[0:i], paths[i:])

        # Problem if we got no paths or unequal original vs new.
        if not origs and not news:
            return do_fail(PN.parsing_no_paths)
        elif len(origs) != len(news):
            return do_fail(PN.parsing_imbalance)

        # Return the RenamePair instances.
        return tuple(
            RenamePair(orig, new)
            for orig, new in zip(origs, news)
        )

    ####
    # Creating the user-defined functions for filtering and renaming.
    ####

    def make_user_defined_func(self, action):
        # Get the user's code, if any.
        user_code = getattr(self, f'{action}_code')
        if not user_code:
            return None

        # Define the text of the code.
        func_name = f'do_{action}'
        code = CON.user_code_fmt.format(
            func_name = func_name,
            user_code = user_code,
            indent = ' ' * self.indent,
        )

        # Create the function via exec() in the context of:
        # - Globals that we want to make available to the user's code.
        # - A locals dict that we can use to return the generated function.
        globs = dict(
            re = re,
            Path = Path,
        )
        locs = {}
        try:
            exec(code, globs, locs)
            return locs[func_name]
        except Exception as e:
            msg = traceback.format_exc(limit = 0)
            p = Problem(PN.user_code_exec, msg)
            self.handle_problem(p)
            return None

    ####
    # A method to execute the steps that process RenamePair instance individually.
    ####

    def processed_rps(self, step):
        self.prefix_len = self.compute_prefix_len()
        seq = self.compute_sequence_iterator()
        for rp in self.rps:
            # The step() call returns a potentially modified RenamePair instance.
            #
            #   - orig: never modified.
            #   - new: set based on the user's renaming code.
            #   - exclude: set true if user's filtering code rejected the instance.
            #   - create_parent: can be set here if a controlled problem occurred.
            #   - clobber: ditto.
            #

            # Check whether the RenamePair has a problem.
            # If so, get the problem-control mechanism, if any.
            # If not, set rp to the return result.
            result = step(rp, next(seq))
            if isinstance(result, Problem):
                control = self.handle_problem(result, rp = rp)
            else:
                control = None
                rp = result

            # Act based on the problem-control and the rp.
            if control == CONTROLS.skip:
                # Skip RenamePair because a problem occurred, but proceed with others.
                continue
            elif control == CONTROLS.clobber:
                # During renaming, the RenamePair will overwrite something.
                yield clone(rp, clobber = True)
            elif control == CONTROLS.create:
                # The RenamePair lacks a parent, but we will create it before renaming.
                yield clone(rp, create_parent = True)
            elif not rp.exclude:
                # No problem: yield unless filtered out by user's code.
                yield rp

    ####
    # The steps that process RenamePair instance individually.
    ####

    def execute_user_filter(self, rp, seq_val):
        if self.filter_code:
            try:
                result = self.filter_func(rp.orig, Path(rp.orig), seq_val, self)
                return rp if result else clone(rp, exclude = True)
            except Exception as e:
                return Problem(PN.filter_code_invalid, e, rp.orig)
        else:
            return rp

    def execute_user_rename(self, rp, seq_val):
        if self.rename_code:
            # Compute the new path.
            try:
                new = self.rename_func(rp.orig, Path(rp.orig), seq_val, self)
            except Exception as e:
                return Problem(PN.rename_code_invalid, e, rp.orig)
            # Validate its type and return a modified RenamePair instance.
            if isinstance(new, (str, Path)):
                return clone(rp, new = str(new))
            else:
                typ = type(new).__name__
                return Problem(PN.rename_code_bad_return, typ, rp.orig)
        else:
            return rp

    def check_orig_exists(self, rp, seq_val):
        if self.path_exists(rp.orig):
            return rp
        else:
            return Problem(PN.missing)

    def check_orig_new_differ(self, rp, seq_val):
        if rp.equal:
            return Problem(PN.equal)
        else:
            return rp

    def check_new_not_exists(self, rp, seq_val):
        # The problem is conditional on ORIG and NEW being different
        # to avoid pointless reporting of multiple problems in such cases.
        if self.path_exists(rp.new) and not rp.equal:
            return Problem(PN.existing)
        else:
            return rp

    def check_new_parent_exists(self, rp, seq_val):
        if self.path_exists(str(Path(rp.new).parent)):
            return rp
        else:
            return Problem(PN.parent)

    def prepare_new_groups(self):
        # Organize rps into dict-of-list, keyed by the new path.
        self.new_groups = {}
        for rp in self.rps:
            self.new_groups.setdefault(rp.new, []).append(rp)

    def check_new_collisions(self, rp, seq_val):
        g = self.new_groups[rp.new]
        if len(g) == 1:
            return rp
        else:
            return Problem(PN.colliding)

    ####
    # Methods related to problem control.
    ####

    def handle_problem(self, f, rp = None):
        # Takes a Problem and optionally a RenamePair.
        #
        # - Determines whether a problem-control is active for the Problem type.
        # - Stores an Problem containing the Problem information and the RenamePair.
        # - Returns the control (which might be None).
        #
        control = self.control_lookup.get(f.name, None)
        p = Problem(f.name, msg = f.msg, rp = rp)
        self.problems[control].append(p)
        return control

    @property
    def failed(self):
        # The RenamingPlan has failed if there are any uncontrolled problems.
        return bool(self.uncontrolled_problems)

    @property
    def uncontrolled_problems(self):
        return self.problems[None]

    ####
    # Sequence number and common prefix.
    ####

    def compute_sequence_iterator(self):
        return iter(range(self.seq_start, sys.maxsize, self.seq_step))

    def compute_prefix_len(self):
        origs = tuple(rp.orig for rp in self.rps)
        return len(commonprefix(origs))

    def strip_prefix(self, orig):
        i = self.prefix_len
        return orig[i:] if i else orig

    ####
    # Files system operations.
    ####

    def initialize_file_sys(self, file_sys):
        # Currently the file system is stored as a dict mapping each
        # existing path to True. Later, we might need the dict values
        # to hold additional information.
        #
        # We build an independent copy of the file system because
        # the rename_paths() method will modify the dict.
        if file_sys is None:
            return None
        elif isinstance(file_sys, dict):
            return deepcopy(file_sys)
        else:
            try:
                return {
                    path : self.DEFAULT_FILE_SYS_VAL
                    for path in file_sys
                }
            except Exception as e:
                raise BmvError.new(e, msg = Problem.format_for(PN.invalid_file_sys))

    def path_exists(self, p):
        if self.file_sys is None:
            # Check the real file system.
            return Path(p).exists()
        else:
            # Or check the fake file system added for testing purposes.
            # In this context, assume that '.' always exists so that the
            # user/tester does not have to include explicitly.
            p = str(p)
            return p in self.file_sys or p == '.'

    def rename_paths(self):
        # Don't rename more than once.
        if self.has_renamed:
            raise BmvError(PF.rename_done_already)
        else:
            self.has_renamed = True

        # Ensure than we have prepare, and raise it failed.
        self.prepare()
        if self.failed:
            raise BmvError(PF.prepare_failed, problems = self.problems[None])

        # Rename paths.
        if self.file_sys is None:
            # On the real file system.
            for rp in self.rps:
                if rp.create_parent:
                    par = Path(rp.new).parent
                    Path.mkdir(par, parents = True, exists_ok = True)
                Path(rp.orig).rename(rp.new)
        else:
            # Or in the fake file system.
            for rp in self.rps:
                if rp.create_parent:
                    for par in Path(rp.new).parents:
                        self.file_sys[str(par)] = self.DEFAULT_FILE_SYS_VAL
                self.file_sys[rp.new] = self.file_sys.pop(rp.orig)

    ####
    # The RenamingPlan as a dict.
    ####

    @property
    def as_dict(self):
        return dict(
            # Primary arguments from user.
            inputs = self.inputs,
            structure = self.structure,
            rename_code = self.rename_code,
            filter_code = self.filter_code,
            indent = self.indent,
            seq_start = self.seq_start,
            seq_step = self.seq_step,
            file_sys = self.file_sys,
            # Problem controls.
            skip = self.skip,
            clobber = self.clobber,
            create = self.create,
            # Other.
            prefix_len = self.prefix_len,
            rename_pairs = [
                asdict(rp)
                for rp in self.rps
            ],
            problems = {
                control : [asdict(f) for f in fs]
                for control, fs in self.problems.items()
            },
        )

    def validated_pnames(self, control, pnames):
        if isinstance(pnames, str):
            pnames = pnames.split()

        if not pnames:
            return ()

        all_choices = Problem.names_for(control)
        invalid = tuple(
            nm
            for nm in pnames
            if not (nm in all_choices or nm == CON.all)
        )

        if invalid:
            pn = ', '.join(pnames)
            msg = PF.invalid_control.format(control, pn)
            raise BmvError(msg)
        elif CON.all in pnames:
            return all_choices
        else:
            return tuple(pnames)

    def build_control_lookup(self):
        lookup = {}
        for c in CONTROLS.keys():
            for pname in getattr(self, c):
                if pname in lookup:
                    fmt = Problem.format_for(PN.conflicting_controls)
                    msg = fmt.format(pname, lookup[pname], c)
                    raise BmvError(msg)
                else:
                    lookup[pname] = c
        return lookup

