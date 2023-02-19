import re
import sys
import traceback

from copy import deepcopy
from dataclasses import asdict, replace as clone
from itertools import groupby
from os.path import commonprefix
from pathlib import Path
from short_con import constants

from .utils import (
    CON,
    EXISTENCES,
    MSG_FORMATS as MF,
    MvsError,
    RenamePair,
    STRUCTURES,
    existence_status,
    is_valid_path_type,
    paths_have_same_type,
)

from .problems import (
    CONTROLS,
    PROBLEM_NAMES as PN,
    PROBLEM_FORMATS as PF,
    Problem,
)

class RenamingPlan:

    # Special values used by self.tracking_index.
    #
    # During rename_paths(), we track progress via self.tracking_index. It has
    # two special values (shown below in TRACKING). Otherwise, a non-negative
    # value indicates which RenamePair we are currently trying to rename. If an
    # unexpected failure occurs, that index tells us which RenamePair failed.
    # API users of RenamingPlan who care can catch the exception and infer
    # which paths were renamed and which were not. Similarly, CliRenamer logs
    # the necessary information to figure that out.
    #
    TRACKING = constants('Tracking', dict(
        not_started = -1,
        done = None,
    ))

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
                 # Problem controls.
                 skip = None,
                 clobber = None,
                 create = None,
                 ):

        # Input paths, input structure, and RenamePair instances.
        self.inputs = tuple(inputs)
        self.structure = structure or STRUCTURES.flat
        self.rps = tuple()

        # User-supplied code.
        self.rename_code = rename_code
        self.filter_code = filter_code
        self.filter_func = None
        self.rename_func = None
        self.indent = indent
        self.seq_start = seq_start
        self.seq_step = seq_step
        self.prefix_len = 0

        # Plan state.
        self.has_prepared = False
        self.has_renamed = False
        self.tracking_index = self.TRACKING.not_started
        self.raise_at = None

        # Information used when checking RenamePair instance for problems.
        self.new_groups = None

        # Convert the problem-control inputs (skip, clobber, create)
        # into validated tuples of problem names.
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

    ####
    #
    # Preparation before renaming.
    #
    # This method performs various validations and computations needed before
    # renaming can occur.
    #
    # The method does not return data; it sets self.rps.
    #
    # The method does not raise; rather, when problems occur, they are
    # stored in self.problems based whether/how the user has configured
    # the plan to control them.
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
        self.rename_func = self.make_user_defined_func(CON.code_actions.rename)
        self.filter_func = self.make_user_defined_func(CON.code_actions.filter)
        if self.failed:
            return

        # Run various steps that process the RenamePair instances individually:
        # filtering, computing new paths, and validating.
        #
        # We use the processed_rps() method to execute the step, handle
        # problems appropriately, and yield a potentially-filtered collection
        # of potentially-modified RenamePair instances.
        #
        rp_steps = (
            (None, self.execute_user_filter),
            (None, self.execute_user_rename),
            (None, self.check_orig_exists),
            (None, self.check_orig_type),
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
        # Parses self.inputs. If valid, returns a tuple of RenamePair
        # instances. Otherwise, registers a Problem and returns empty tuple.

        # Helper to handle a Problem and return empty.
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
            # - Group into non-empty vs empty lines.
            # - Ensure exactly two groups of non-empty.
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
            groups = [[], []]
            for i, line in enumerate(self.inputs):
                if line:
                    groups[i % 2].append(line)
            origs, news = groups

        elif self.structure == STRUCTURES.rows:
            # Rows: original-new path pairs, as tab-delimited rows.
            origs = []
            news = []
            for row in self.inputs:
                if row:
                    cells = row.split(CON.tab)
                    if len(cells) == 2 and all(cells):
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

        # If the user code is already a callable, just return it.
        if callable(user_code):
            return user_code

        # Define the text of the code.
        func_name = CON.func_name_fmt.format(action)
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
        # Takes a "step", which is a RenamingPlan method.
        # Executes that method for each RenamePair.
        # Yields potentially-modified RenamePair instances,
        # handling problems along the way.

        # Prepare common-prefix and sequence numbering, which might
        # be used by the user-suppled renaming/filtering code.
        self.prefix_len = self.compute_prefix_len()
        seq = self.compute_sequence_iterator()

        for rp in self.rps:
            # The step() call returns a potentially-modified
            # RenamePair instance or a Problem instance.
            #
            # - orig: never modified.
            # - new: set based on the user's renaming code.
            # - exclude: set true if user's filtering code rejected the instance.
            # - create_parent: can be set here if a controlled problem occurred.
            # - clobber: ditto.
            #

            # Execute the step. If we get a Problem, handle it.
            # Otherwise, set rp to the returned RenamePair.
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
    # Each step returns a Problem, the orignal RenamePair, or
    # a modified RenamePair.
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
        # Key question: is renaming possible?
        # Strict existence not required.
        if self.path_exists(rp.orig, strict = False):
            return rp
        else:
            return Problem(PN.missing)

    def check_orig_type(self, rp, seq_val):
        if is_valid_path_type(rp.orig):
            return rp
        else:
            return Problem(PN.type)

    def check_orig_new_differ(self, rp, seq_val):
        if rp.equal:
            return Problem(PN.equal)
        else:
            return rp

    def check_new_not_exists(self, rp, seq_val):
        # Key question: is renaming necessary?
        # Here the check requires strict existence so we can
        # support case-change-only renamings.
        #
        # The problem is conditional on ORIG and NEW being different
        # to avoid pointless reporting of multiple problems in cases
        # where ORIG does not exist and where it equals NEW.
        if self.path_exists(rp.new, strict = True) and not rp.equal:
            if paths_have_same_type(rp.orig, rp.new):
                return Problem(PN.existing)
            else:
                return Problem(PN.existing_diff)
        else:
            return rp

    def check_new_parent_exists(self, rp, seq_val):
        # Key question: does renaming also require parent creation?
        # Mere existence is sufficient.
        if self.path_exists(Path(rp.new).parent, strict = False):
            return rp
        else:
            return Problem(PN.parent)

    def prepare_new_groups(self):
        # A preparation-step for check_new_collisions().
        # Organize rps into dict-of-list, keyed by the new path.
        self.new_groups = {}
        for rp in self.rps:
            self.new_groups.setdefault(rp.new, []).append(rp)

    def check_new_collisions(self, rp, seq_val):
        g = self.new_groups[rp.new]
        if len(g) == 1:
            return rp
        else:
            others = tuple(rp2.new for rp2 in g)
            if paths_have_same_type(rp.new, *others):
                return Problem(PN.colliding)
            else:
                return Problem(PN.colliding_diff)

    ####
    # Methods related to problem control.
    ####

    def validated_pnames(self, control, pnames):
        # Takes a CONTROLS name and a str or sequence of problem names.
        # Validates that those names are appropropriate for the control.
        # Also handles the "all" shortcut.
        # Returns a tuple of validated problem names.

        # Convert str to sequence.
        if isinstance(pnames, str):
            pnames = pnames.split()

        # Stop if no problem names.
        if not pnames:
            return ()

        # Check that the problem names are valid for the given control.
        all_choices = Problem.names_for(control)
        invalid = tuple(
            nm
            for nm in pnames
            if not (nm in all_choices or nm == CON.all)
        )

        # Either raise or return the validated tuple of problem names.
        if invalid:
            pn = CON.comma_join.join(pnames)
            msg = MF.invalid_control.format(control, pn)
            raise MvsError(msg)
        elif CON.all in pnames:
            return all_choices
        else:
            return tuple(pnames)

    def build_control_lookup(self):
        # Uses the tuples in self.skip, self.create, and self.clobber to return
        # a dict mapping each Problem name that the user wants to control to
        # the desired control mechanism. Raises if the user tries to control
        # the same Problem in different ways.
        lookup = {}
        for c in CONTROLS.keys():
            for pname in getattr(self, c):
                if pname in lookup:
                    msg = MF.conflicting_controls.format(pname, lookup[pname], c)
                    raise MvsError(msg)
                else:
                    lookup[pname] = c
        return lookup

    def handle_problem(self, p, rp = None):
        # Takes a Problem and optionally a RenamePair.
        #
        # - Determines whether a problem-control is active for the problem type.
        # - Stores a new Problem containing original Problem info, plus the RenamePair.
        # - Returns the control (which might be None).
        #
        control = self.control_lookup.get(p.name, None)
        p = Problem(p.name, msg = p.msg, rp = rp)
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

    def path_exists(self, path, strict = False):
        e = EXISTENCES.exists_strict if strict else EXISTENCES.exists
        return existence_status(path) >= e

    def rename_paths(self):
        # Don't rename more than once.
        if self.has_renamed:
            raise MvsError(MF.rename_done_already)
        else:
            self.has_renamed = True

        # Ensure than we have prepare, and raise if it failed.
        self.prepare()
        if self.failed:
            raise MvsError(MF.prepare_failed, problems = self.problems[None])

        # Rename paths.
        for i, rp in enumerate(self.rps):
            self.tracking_index = i
            self.do_rename(rp)
        self.tracking_index = self.TRACKING.done

    def do_rename(self, rp):
        # Takes a RenamePair and executes its renaming.

        # For testing purposes, raise a simulated error at
        # the desired tracking_index.
        if self.tracking_index == self.raise_at:
            raise ZeroDivisionError('SIMULATED_ERROR')

        # Rename.
        if rp.create_parent:
            Path(rp.new).parent.mkdir(parents = True, exist_ok = True)
        p = Path(rp.orig)
        if rp.clobber:
            p.replace(rp.new)
        else:
            p.rename(rp.new)

    ####
    # Other info.
    ####

    @property
    def tracking_rp(self):
        # The RenamePair that was being renamed when rename_paths()
        # raised an exception.
        ti = self.tracking_index
        if ti in (self.TRACKING.not_started, self.TRACKING.done):
            return None
        else:
            return self.rps[ti]

    @property
    def as_dict(self):
        # The plan as a dict.
        return dict(
            # Primary arguments from user.
            inputs = self.inputs,
            structure = self.structure,
            rename_code = self.rename_code,
            filter_code = self.filter_code,
            indent = self.indent,
            seq_start = self.seq_start,
            seq_step = self.seq_step,
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
            tracking_index = self.tracking_index,
            problems = {
                control : [asdict(p) for p in ps]
                for control, ps in self.problems.items()
            },
        )

