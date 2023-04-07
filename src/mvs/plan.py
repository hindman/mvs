import re
import shutil
import sys
import traceback

from copy import deepcopy
from dataclasses import asdict, dataclass
from itertools import groupby
from os.path import commonprefix, samefile
from pathlib import Path
from short_con import constants

from .utils import (
    ANY_EXISTENCE,
    CON,
    EXISTENCES,
    FAILURE_FORMATS as FF,
    FAILURE_NAMES as FN,
    FS_TYPES,
    Failure,
    MSG_FORMATS as MF,
    MvsError,
    NAME_CHANGE_TYPES as NCT,
    PATH_TYPES,
    PROBLEM_FORMATS as PF,
    PROBLEM_NAMES as PN,
    Problem,
    STRUCTURES,
    case_sensitivity,
    determine_path_type,
    get_source_code,
    is_non_empty_dir,
    path_existence_and_type,
)

@dataclass
class Renaming:
    # A data object to hold an original path and the corresponding new path.

    # Paths.
    orig: str
    new: str

    # Path EXISTENCES.
    exist_orig: int = None
    exist_new: int = None
    exist_new_parent: int = None

    # Path types.
    type_orig: str = None
    type_new: str = None

    # The renaming type and whether orig and new have the same parents.
    name_change_type: str = None
    same_parents: bool = None

    # Whether the orig and new paths points to non-empty directories.
    full_orig: bool = False
    full_new: bool = False

    # Attributes for problems.
    # - Problem with the Renaming, if any.
    # - Whether user code filtered out the rn.
    # - Whether rn caused a Problem that will halt the RenamingPlan.
    # - Whether rn should be skipped due to a Problem.
    # - Whether to create new-parent before renaming.
    # - Whether renaming will clobber something.
    # - Whether renaming will involve case-change-only renaming (ie self-clobber).
    problem: Problem = None
    exclude: bool = False
    halt: bool = False
    skip: bool = False
    create: bool = False
    clobber: bool = False
    clobber_self: bool = False

    @property
    def equal(self):
        return self.orig == self.new

    @property
    def prob_name(self):
        if self.problem is None:
            return None
        else:
            return self.problem.name

    @property
    def halt_or_skip(self):
        return bool(self.halt or self.skip)

    @property
    def formatted(self):
        prefix = (
            f'# Problem: {self.prob_name}\n' if self.halt_or_skip
            else ''
        )
        return f'{prefix}{self.orig}\n{self.new}\n'

class RenamingPlan:

    # Special values used by self.tracking_index.
    #
    # During rename_paths(), we track progress via self.tracking_index. It has
    # two special values (shown below in TRACKING). Otherwise, a non-negative
    # value indicates which Renaming we are currently trying to rename. If an
    # unexpected failure occurs, that index tells us which Renaming failed.
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
                 # Problem handling.
                 skip = None,
                 strict = False,
                 ):

        # Input paths and structure.
        self.inputs = tuple(inputs)
        self.structure = structure or STRUCTURES.flat

        # Based on the inputs we begin with the full universe of
        # Renaming instances. During processing, those rns
        # get put into four buckes:
        # - active renamings
        # - filtered out by user code
        # - skipped via problem-control
        # - those having problems that will cause plan halt.
        # - initial N of rns (before filtering, etc)
        self.n_initial = None
        self.rns = []
        self.filtered = []
        self.skipped = []
        self.halts = []

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
        self.call_at = None

        # Information used when checking Renaming instance for problems.
        self.new_groups = None
        self.new_collision_key_func = (
            str if case_sensitivity() == FS_TYPES.case_sensitive else
            str.lower
        )

        # Validate and standardize the user's problem controls.
        # Then merge the defaults problem controls with the user's into
        # a lookup dict mapping each Problem name to its control mechanism.
        self.strict = bool(strict)

        # try:
        #     self.controls = ProblemControl.merge(controls)
        # except MvsError as e:
        #     raise e
        # except Exception as e:
        #     raise MvsError(MF.invalid_controls, controls = controls)
        # self.control_lookup = ProblemControl.merge(
        #     ProblemControl.DEFAULTS,
        #     self.controls,
        #     ProblemControl.HALT_ALL if self.strict else (),
        #     want_map = True,
        # )

        # Failures that will halt the RenamingPlan before any renaming.
        self.failures = []

    ####
    #
    # Preparation before renaming.
    #
    # This method performs various validations and computations needed before
    # renaming can occur.
    #
    # The method does not return data; it sets self.rns.
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

        # Get the input paths and parse them to get Renaming instances.
        self.rns = self.parse_inputs()
        self.n_initial = len(self.rns)
        if self.failed:
            return

        # Create the renaming and filtering functions from
        # user-supplied code, if any was given.
        self.filter_func = self.make_user_defined_func(CON.code_actions.filter)
        self.rename_func = self.make_user_defined_func(CON.code_actions.rename)
        if self.failed:
            return

        # Run various steps that process the Renaming instances individually:
        # setting their path existence statuses and path types; filtering;
        # computing new paths; and checking for problems.
        rn_steps = (
            (self.set_exists_and_types, None),
            (self.execute_user_filter, None),
            (self.execute_user_rename, None),
            (self.set_exists_and_types, None),
            (self.check_equal, None),
            (self.check_orig_exists, None),
            (self.check_orig_type, None),
            (self.check_new_exists, None),
            (self.check_new_parent_exists, None),
            (self.check_new_collisions, self.prepare_new_groups),
        )
        for step, prep_step in rn_steps:
            # Run preparatory step.
            if prep_step:
                prep_step()

            # Prepare common-prefix and sequence numbering, which might
            # be used by the user-suppled renaming/filtering code.
            self.prefix_len = self.compute_prefix_len()
            seq = self.compute_sequence_iterator()

            # Execute the step for each rn. Some steps set attributes on the rn
            # to guide subsequent filtering, skipping, clobbering, etc.
            active = []
            for rn in self.rns:
                # If the step returns a Problem, handle it and set the
                # corresponding problem-related attributes on rn.
                prob = step(rn, next(seq))
                if prob:
                    rn.problem = prob
                    control = self.control_lookup[prob.name]
                    if control:
                        setattr(rn, control, True)
                # Add each resulting rn to the appropriate list.
                xs = (
                    self.filtered if rn.exclude else
                    self.skipped if rn.skip else
                    self.halts if rn.halt else
                    active
                )
                xs.append(rn)
            self.rns = active

        # Register problem if everything was filtered out.
        if not self.rns:
            self.handle_failure(FN.all_filtered)

    ####
    # Parsing inputs to obtain the original and, in some cases, new paths.
    ####

    def parse_inputs(self):
        # Parses self.inputs. If valid, returns a tuple of Renaming
        # instances. Otherwise, registers a Failure and returns empty list.

        # Helper to handle a Failure and return empty.
        def do_fail(name, *xs):
            self.handle_failure(name, *xs)
            return []

        # If we have rename_code, inputs are just original paths.
        if self.rename_code:
            rns = [
                Renaming(orig, None)
                for orig in self.inputs
                if orig
            ]
            if rns:
                return rns
            else:
                return do_fail(FN.parsing_no_paths)

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
                return do_fail(FN.parsing_paragraphs)

        elif self.structure == STRUCTURES.pairs:
            # Pairs: original path, new path, original path, etc.
            groups = [[], []]
            i = 0
            for line in self.inputs:
                if line:
                    groups[i % 2].append(line)
                    i += 1
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
                        return do_fail(FN.parsing_row, row)

        else:
            # Flat: like paragraphs without the blank-line delimiter.
            paths = [line for line in self.inputs if line]
            i = len(paths) // 2
            origs, news = (paths[0:i], paths[i:])

        # Failure if we got no paths or unequal original vs new.
        if not origs and not news:
            return do_fail(FN.parsing_no_paths)
        elif len(origs) != len(news):
            return do_fail(FN.parsing_imbalance)

        # Return the Renaming instances.
        return [
            Renaming(orig, new)
            for orig, new in zip(origs, news)
        ]

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
            tb = traceback.format_exc(limit = 0)
            self.handle_failure(FN.user_code_exec, action, tb)
            return None

    ####
    # The steps that process Renaming instance individually.
    # Each step returns a Problem or None.
    ####

    def set_exists_and_types(self, rn, seq_val):
        # This step is called twice, and the beginning and then after user-code
        # for filtering and renaming has been executed. The initial call sets
        # information for rn.orig and, if possible, rn.new. The second call
        # handles rn.new if we have not done so already. The attributes set
        # here are used for most of the subsequent steps.

        # Handle attributes related to rn.orig.
        if rn.exist_orig is None:
            # Existence, type, and non-empty dir.
            e, pt = path_existence_and_type(rn.orig)
            rn.exist_orig = e
            rn.type_orig = pt
            if pt == PATH_TYPES.directory:
                rn.full_orig = is_non_empty_dir(rn.orig)

        # Handle attributes related to rn.new.
        if rn.exist_new is None and rn.new is not None:
            po = Path(rn.orig)
            pn = Path(rn.new)
            # Existence, type, and non-empty dir.
            e, pt = path_existence_and_type(rn.new)
            rn.exist_new = e
            rn.type_new = pt
            if pt == PATH_TYPES.directory:
                rn.full_new = is_non_empty_dir(rn.new)
            # Existence of parent.
            e, _ = path_existence_and_type(pn.parent)
            rn.exist_new_parent = e
            # Attributes characterizing the renaming.
            rn.same_parents = (
                False if rn.exist_new_parent == EXISTENCES.missing else
                samefile(po.parent, pn.parent)
            )
            rn.name_change_type = (
                NCT.noop if po.name == pn.name else
                NCT.case_change if po.name.lower() == pn.name.lower() else
                NCT.name_change
            )

        return None

    def execute_user_filter(self, rn, seq_val):
        if self.filter_code:
            try:
                keep = self.filter_func(rn.orig, Path(rn.orig), seq_val, self)
                if not keep:
                    rn.exclude = True
            except Exception as e:
                return Problem(PN.filter, e, rn.orig)
        return None

    def execute_user_rename(self, rn, seq_val):
        if self.rename_code:
            # Compute the new path.
            try:
                new = self.rename_func(rn.orig, Path(rn.orig), seq_val, self)
            except Exception as e:
                return Problem(PN.rename, e, rn.orig)
            # Validate its type and either set rn.new or return Problem.
            if isinstance(new, (str, Path)):
                rn.new = str(new)
            else:
                typ = type(new).__name__
                return Problem(PN.rename, typ, rn.orig)
        return None

    def check_equal(self, rn, seq_val):
        if rn.equal:
            return Problem(PN.equal)
        else:
            return None

    def check_orig_exists(self, rn, seq_val):
        # Key question: is renaming possible?
        if rn.exist_orig in ANY_EXISTENCE:
            return None
        else:
            return Problem(PN.missing)

    def check_orig_type(self, rn, seq_val):
        if rn.type_orig in (PATH_TYPES.file, PATH_TYPES.directory):
            return None
        else:
            return Problem(PN.type)

    def check_new_exists(self, rn, seq_val):
        # Handle situation where rn.new does not exist in any sense.
        # In this case, we can rename freely, regardless of file
        # system type or other renaming details.
        new_exists = (rn.exist_new in ANY_EXISTENCE)
        if not new_exists:
            return None

        # Determine the type of Problem to return if clobbering would occur.
        #
        # TODO: need to add a check for rn.type_new of OTHER. If
        # so return Problem(exists, other).
        #
        if rn.type_new == PATH_TYPES.directory and rn.full_new:
            clobber_prob = Problem(PN.exists_full)
        elif rn.type_orig == rn.type_new:
            clobber_prob = Problem(PN.exists)
        else:
            clobber_prob = Problem(PN.exists_diff)

        # Handle the simplest file systems: case-sensistive or
        # case-insensistive. Since rn.new exists, we have clobbering
        if case_sensitivity() != FS_TYPES.case_preserving: # pragma: no cover
            return clobber_prob

        # Handle case-preserving file system where rn.orig and rn.new have
        # different parent directories. Since the parent directories differ,
        # case-change-only renaming (ie, self clobber) is not at issue,
        # so we have regular clobbering.
        if not rn.same_parents:
            return clobber_prob

        # Handle case-preserving file system where rn.orig and rn.new have
        # the same parent, which means the renaming involves only changes
        # to the name-portion of the path.
        if rn.name_change_type == NCT.noop:
            # New exists because rn.orig and rn.new are functionally the same
            # path. User inputs implied that a renaming was desired (rn.orig
            # and rn.new were not equal) but the only difference lies in the
            # casing of the parent path. By policy, mvs does not rename parents.
            return Problem(PN.same)
        elif rn.name_change_type == NCT.case_change:
            if rn.exist_new == EXISTENCES.exists_case:
                # User inputs implied that a case-change renaming
                # was desired, but the path's name-portion already
                # agrees with the file system, so renaming is impossible.
                return Problem(PN.recase)
            else:
                # User wants a case-change renaming (self-clobber).
                rn.clobber_self = True
                return None
        else:
            # User wants a name-change, and it would clobber something else.
            return clobber_prob

    def check_new_parent_exists(self, rn, seq_val):
        # Key question: does renaming also require parent creation?
        # Any type of existence is sufficient.
        if rn.exist_new_parent in ANY_EXISTENCE:
            return None
        else:
            return Problem(PN.parent)

    def prepare_new_groups(self):
        # A preparation-step for check_new_collisions().
        # Organize rns into dict-of-list, keyed by the new path.
        # Those keys are stored as-is for case-sensistive file
        # systems and in lowercase for non-sensistive systems.
        self.new_groups = {}
        for rn in self.rns:
            k = self.new_collision_key_func(rn.new)
            self.new_groups.setdefault(k, []).append(rn)

    def check_new_collisions(self, rn, seq_val):
        # Checks for collisions among all of the new paths in the RenamingPlan.
        # If any, returns the most serious problem: (1) collisions with
        # non-empty directories, (2) collisions with a path of a different
        # type, or (3) regular collisions.
        #
        # Collisions occur between (A) the path-type of rn.orig, (B) the
        # path-types of all OTHER.orig, and (C) the path-types of any OTHER.new
        # that happen to exist.

        # Get the other Renaming instances that have the same new-path as the
        # current rn. If rn.new is unique, there is no problem.
        k = self.new_collision_key_func(rn.new)
        others = [o for o in self.new_groups[k] if o is not rn]
        if not others:
            return None

        # Check for collisions with non-empty directories.
        if any(o.full_orig or o.full_new for o in others):
            return Problem(PN.collides_full)

        # Check for collisions with a different path type.
        pt = rn.type_orig
        for o in others:
            if o.type_orig != pt or (o.type_new and o.type_new != pt):
                return Problem(PN.collides_diff)

        # Otherwise, it's a regular collision.
        return Problem(PN.collides)

    ####
    # Methods related to problem control.
    ####

    def handle_failure(self, name, *xs):
        # Takes name/args to create a Failure and then stores it.
        f = Failure(name, *xs)
        self.failures.append(f)

    @property
    def failed(self):
        return bool(self.failures or self.halts)

    ####
    # Sequence number and common prefix.
    ####

    def compute_sequence_iterator(self):
        return iter(range(self.seq_start, sys.maxsize, self.seq_step))

    def compute_prefix_len(self):
        origs = tuple(rn.orig for rn in self.rns)
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
            raise MvsError(
                MF.prepare_failed,
                failures = self.failures,
                halts = self.halts,
            )

        # Rename paths.
        for i, rn in enumerate(self.rns):
            self.tracking_index = i
            self.do_rename(rn)
        self.tracking_index = self.TRACKING.done

    def do_rename(self, rn):
        # Takes a Renaming and executes its renaming.

        # For testing purposes, call any needed code in
        # the middle of renaming -- eg, to raise an error
        # of some kind or to affect the file system in some way.
        if self.call_at and self.tracking_index == self.call_at[0]:
            self.call_at[1](self)

        # Set up Path instance.
        po = Path(rn.orig)
        pn = Path(rn.new)

        # Create new parent if requested.
        if rn.create:
            pn.parent.mkdir(parents = True, exist_ok = True)

        # If new path exists already, deal with it before
        # we attempt to renaming from rn.orig to rn.new.
        # We do this for a few reasons.
        #
        # (1) We want to make a best-effort to avoid unintended
        # clobbering, whether due to race conditions (creation
        # of rn.new since the problem-checks were performed)
        # or due to interactions among the renamings (eg, multiple
        # collisions among rn.new values).
        #
        # (2) We don't want the renamed path to inherit casing from
        # the existing rn.new, which occurs on case-preseving systems.
        #
        # (3) Python's path renaming functions fail on some
        # systems in the face of clobbering, and we don't want
        # to deal with those OS-dependent complications.
        #
        if pn.exists():
            if rn.clobber_self:
                # User requested case-change renaming. No problem.
                pass
            elif rn.clobber:
                # User requested a clobber for this Renaming.
                # Make sure the clobber victim is (still) a supported path type.
                # Select the appropriate deletion operation based on the path
                # type and the user's control setting regarding non-empty dirs.
                pt = determine_path_type(rn.new)
                if pt == PATH_TYPES.other:
                    raise MvsError(
                        MF.unsupported_clobber,
                        orig = rn.orig,
                        new = rn.new,
                    )
                elif pt == PATH_TYPES.file:
                    pn.unlink()
                elif self.control_lookup[PN.exists_full] == CONTROLS.clobber:
                    shutil.rmtree(rn.new)
                else:
                    pn.rmdir()
            else:
                # An unrequested clobber.
                raise MvsError(
                    MF.unrequested_clobber,
                    orig = rn.orig,
                    new = rn.new,
                )

        # Rename.
        po.rename(rn.new)

    ####
    # Other info.
    ####

    @property
    def creates(self):
        return [rn for rn in self.rns if rn.create]

    @property
    def clobbers(self):
        return [rn for rn in self.rns if rn.clobber]

    @property
    def tracking_rn(self):
        # The Renaming that was being renamed when rename_paths()
        # raised an exception.
        ti = self.tracking_index
        if ti in (self.TRACKING.not_started, self.TRACKING.done):
            return None
        else:
            return self.rns[ti]

    @property
    def as_dict(self):
        # The plan as a dict.
        return dict(
            # Primary arguments from user.
            inputs = self.inputs,
            structure = self.structure,
            rename_code = get_source_code(self.rename_code),
            filter_code = get_source_code(self.filter_code),
            indent = self.indent,
            seq_start = self.seq_start,
            seq_step = self.seq_step,
            controls = self.controls,
            strict = self.strict,
            # Renaming instances.
            renamings = [asdict(rn) for rn in self.rns],
            filtered = [asdict(rn) for rn in self.filtered],
            skipped = [asdict(rn) for rn in self.skipped],
            halts = [asdict(rn) for rn in self.halts],
            # Other.
            failures = [asdict(f) for f in self.failures],
            prefix_len = self.prefix_len,
            tracking_index = self.tracking_index,
        )

