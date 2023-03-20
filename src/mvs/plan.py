import re
import sys
import traceback

from copy import deepcopy
from dataclasses import asdict
from itertools import groupby
from os.path import commonprefix, samefile
from pathlib import Path
from short_con import constants

from .utils import (
    CON,
    EXISTENCES,
    FS_TYPES,
    MSG_FORMATS as MF,
    MvsError,
    NAME_CHANGE_TYPES as NCT,
    PATH_TYPES,
    RenamePair,
    STRUCTURES,
    file_system_case_sensitivity,
    path_existence_and_type,
)

from .problems import (
    CONTROLS,
    PROBLEM_FORMATS as PF,
    PROBLEM_NAMES as PN,
    Problem,
    ProblemControl,
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

    # Default problem controls.
    DEFAULT_CONTROLS = (
        f'{CONTROLS.skip}-{PN.equal}',
        f'{CONTROLS.skip}-{PN.same}',
        f'{CONTROLS.skip}-{PN.recase}',
    )

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
                 controls = None,
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

        # Convert the problem-control inputs into a normalized tuple. Then
        # build a lookup mapping each Problem name to the user's requested
        # control mechanism.
        if controls is None:
            controls = self.DEFAULT_CONTROLS
        self.controls = self.normalized_controls(controls)
        self.control_lookup = self.build_control_lookup(self.controls)

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
        # setting their path existence statuses and path types; filtering;
        # computing new paths; and checking for problems.
        #
        # We use the processed_rps() method to execute the step, handle
        # problems appropriately, and yield a potentially-filtered collection
        # of potentially-modified RenamePair instances.
        #
        rp_steps = (
            (self.set_exists_and_types, None),
            (self.execute_user_filter, None),
            (self.execute_user_rename, None),
            (self.set_exists_and_types, None),
            (self.check_orig_exists, None),
            (self.check_orig_type, None),
            (self.check_new_exists, None),
            (self.check_new_parent_exists, None),
            (self.check_new_collisions, self.prepare_new_groups),
        )
        for step, prep_step in rp_steps:
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
            # The step() call might modify the rp and will return
            # a Problem or None.
            #
            # - orig: never modified.
            # - new: set based on the user's renaming code.
            # - exclude: set true if user's filtering code rejected the instance.
            # - create_parent: can be set here if a controlled problem occurred.
            # - clobber: ditto.
            #

            # Execute the step. If we get a Problem, handle it and
            # determine whether a control for it is active.
            prob = step(rp, next(seq))
            if prob is None:
                control = None
            else:
                control = self.handle_problem(prob, rp = rp)

            # Act based on the problem-control and the rp.
            if control == CONTROLS.skip:
                # Skip RenamePair because a problem occurred, but proceed with others.
                continue
            elif control == CONTROLS.clobber:
                # During renaming, the RenamePair will overwrite something.
                rp.clobber = True
                yield rp
            elif control == CONTROLS.create:
                # The RenamePair lacks a parent, but we will create it before renaming.
                rp.create_parent = True
                yield rp
            elif not rp.exclude:
                # No problem: yield unless filtered out by user's code.
                yield rp

    ####
    # The steps that process RenamePair instance individually.
    # Each step returns a Problem or None.
    ####

    def set_exists_and_types(self, rp, seq_val):
        # This step is called twice, and the beginning and then after user-code
        # for filtering and renaming has been executed. The initial call sets
        # information for rp.orig and, if possible, rp.new. The second call
        # handles rp.new if we have not done so already. The attributes set
        # here are used for most of the subsequent steps.
        if rp.exist_orig is None:
            # Set existence and type for rp.orig.
            e, pt = path_existence_and_type(rp.orig)
            rp.exist_orig = e
            rp.type_orig = pt
        if rp.exist_new is None and rp.new is not None:
            po = Path(rp.orig)
            pn = Path(rp.new)
            # Set existence and type for rp.new.
            e, pt = path_existence_and_type(rp.new)
            rp.exist_new = e
            rp.type_new = pt
            # Set existence for rp.new parent.
            e, _ = path_existence_and_type(pn.parent)
            rp.exist_new_parent = e
            # Set the attribute characterizing the renaming.
            rp.same_parents = (
                False if rp.exist_new_parent == EXISTENCES.missing else
                samefile(po.parent, pn.parent)
            )
            rp.name_change_type = (
                NCT.noop if po.name == pn.name else
                NCT.case_change if po.name.lower() == pn.name.lower() else
                NCT.name_change
            )
        return None

    def execute_user_filter(self, rp, seq_val):
        if self.filter_code:
            try:
                keep = self.filter_func(rp.orig, Path(rp.orig), seq_val, self)
                if not keep:
                    rp.exclude = True
            except Exception as e:
                return Problem(PN.filter_code_invalid, e, rp.orig)
        return None

    def execute_user_rename(self, rp, seq_val):
        if self.rename_code:
            # Compute the new path.
            try:
                new = self.rename_func(rp.orig, Path(rp.orig), seq_val, self)
            except Exception as e:
                return Problem(PN.rename_code_invalid, e, rp.orig)
            # Validate its type and either set rp.new or return Problem.
            if isinstance(new, (str, Path)):
                rp.new = str(new)
            else:
                typ = type(new).__name__
                return Problem(PN.rename_code_bad_return, typ, rp.orig)
        return None

    def check_orig_exists(self, rp, seq_val):
        # Key question: is renaming possible?
        # Strict existence not required.
        if rp.exist_orig >= EXISTENCES.exists:
            return None
        else:
            return Problem(PN.missing)

    def check_orig_type(self, rp, seq_val):
        if rp.type_orig in (PATH_TYPES.file, PATH_TYPES.directory):
            return None
        else:
            return Problem(PN.type)

    def check_new_exists(self, rp, seq_val):
        # Convenience variables:
        # - Whether rp.new exists in any sense.
        # - The type of problem to return if clobbering would occur.
        new_exists = (rp.exist_new >= EXISTENCES.exists)
        clobber_prob = (
            Problem(PN.existing) if rp.type_orig == rp.type_new else
            Problem(PN.existing_diff)
        )

        # Handle path equality. In this case, renaming is
        # impossible and user input did not request it.
        if rp.equal:
            return Problem(PN.equal)

        # Handle situation where rp.new does not exist in any sense.
        # In this case, we can rename freely, regardless of file
        # system type or other renaming details.
        if not new_exists:
            return None

        # Handle the simplest file systems: case-sensistive or
        # case-insensistive. Since rp.new exists, we have clobbering
        if file_system_case_sensitivity() != FS_TYPES.case_preserving:
            return clobber_prob

        # Handle case-preserving file system where rp.orig and rp.new have
        # different parent directories. Since the parent directories differ,
        # case-change-only renaming (ie, self clobber) is not at issue,
        # so we have regular clobbering.
        if not rp.same_parents:
            return clobber_prob

        # Handle case-preserving file system where rp.orig and rp.new have
        # the same parent, which means the renaming involves only changes
        # to the name-portion of the path.
        if rp.name_change_type == NCT.noop:
            # New exists because rp.orig and rp.new are functionally the same
            # path. User inputs implied that a renaming was desired (rp.orig
            # and rp.new were not equal) but the only difference lies in the
            # casing of the parent path. By policy, mvs does not rename parents.
            return Problem(PN.same)
        elif rp.name_change_type == NCT.case_change:
            if rp.exist_new >= EXISTENCES.exists_strict:
                # User inputs implied that a case-change renaming
                # was desired, but the path's name-portion already
                # agrees with the file system, so renaming is impossible.
                return Problem(PN.recase)
            else:
                # User wants a case-change renaming (self-clobber): no problem.
                return None
        else:
            # User wants a name-change, and it would clobber something else.
            return clobber_prob

    def check_new_parent_exists(self, rp, seq_val):
        # Key question: does renaming also require parent creation?
        # Any type of existence is sufficient.
        if rp.exist_new_parent >= EXISTENCES.exists:
            return None
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
            # No collisions with rp.new.
            return None
        elif not rp.exist_orig >= EXISTENCES.exists:
            # If rp.orig does not exist, do need to report any
            # errors related to collisions with its rp.new.
            return None
        else:
            # Check for collisions among new paths. That implies checking any
            # other paths (orig or new) that exist. I have some lingering
            # doubts about this logic and how reporting for this problem should
            # relate to reporting for others.
            types = []
            for other in g:
                if other.exist_orig:
                    types.append(other.type_orig)
                if other.exist_new:
                    types.append(other.type_new)
            if all(rp.type_orig == t for t in types):
                return Problem(PN.colliding)
            else:
                return Problem(PN.colliding_diff)

    ####
    # Methods related to problem control.
    ####

    @staticmethod
    def normalized_controls(controls):
        # Takes user's input controls and returns them as
        # a tuple of normalized values using hyphens.
        if controls is None:
            return ()
        elif isinstance(controls, str):
            return tuple(controls.split())
        else:
            try:
                return tuple(controls)
            except Exception as e:
                raise MvsError(MF.invalid_controls, controls = controls)

    @staticmethod
    def build_control_lookup(pc_names):
        # Takes an iterable of ProblemControl names.
        #
        # Returns a dict mapping each Problem name that the user wants
        # to control to the desired control mechanism.
        #
        # Raises if the user (1) supplies an invalid problem control,
        # (2) suplies a negative problem control, or
        # (3) tries to control the same Problem in different ways.
        pcs = tuple(
            ProblemControl(name)
            for name in pc_names
        )
        lookup = {}
        for pc in pcs:
            pname = pc.pname
            if pc.no:
                msg = MF.invalid_control.format(pc.name)
                raise MvsError(msg)
            elif pname in lookup:
                fmt = MF.conflicting_controls
                msg = fmt.format(pname, lookup[pname], pc.control)
                raise MvsError(msg)
            else:
                lookup[pname] = pc.control
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
            controls = self.controls,
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

