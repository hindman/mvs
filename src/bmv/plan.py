import re
import sys
import traceback

from copy import deepcopy
from dataclasses import asdict, replace as clone
from itertools import groupby
from os.path import commonprefix
from pathlib import Path

from .constants import (
    CON,
    FAIL,
    CONTROLS,
    CONTROLLABLES,
    STRUCTURES,
)

from .data_objects import (
    RenamePair,
    Failure,
    ParseFailure,
    UserCodeExecFailure,
    OptsFailure,
    NoPathsFailure,
    RpFilterFailure,
    RpRenameFailure,
    RpEqualFailure,
    RpMissingFailure,
    RpMissingParentFailure,
    RpExistsFailure,
    RpCollsionFailure,
    BmvError,
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
                 # Failure controls.
                 skip_equal = False,
                 skip_missing = False,
                 skip_missing_parent = False,
                 create_missing_parent = False,
                 skip_existing_new = False,
                 clobber_existing_new = False,
                 skip_colliding_new = False,
                 clobber_colliding_new = False,
                 skip_failed_rename = False,
                 skip_failed_filter = False,
                 keep_failed_filter = False,
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

        self.skip_failed_filter = skip_failed_filter
        self.skip_failed_rename = skip_failed_rename
        self.skip_equal = skip_equal
        self.skip_missing = skip_missing
        self.skip_missing_parent = skip_missing_parent
        self.skip_existing_new = skip_existing_new
        self.skip_colliding_new = skip_colliding_new
        self.clobber_existing_new = clobber_existing_new
        self.clobber_colliding_new = clobber_colliding_new
        self.keep_failed_filter = keep_failed_filter
        self.create_missing_parent = create_missing_parent

        # Get a dict mapping each Failure type to the user's requested control
        # mechanism (skip, keep, create, clobber).
        result = validated_failure_controls(self)
        if isinstance(result, Failure):
            raise BmvError(result.msg)
        else:
            self.fail_config = result

        # Failures that occur during the prepare() phase are stored in a dict.
        # A failure can be either controlled (as requested by the user) or not.
        # The dict maps each control mechanism to the failures that were
        # controlled by that mechanism. If the dict ends up having any
        # uncontrolled failures (under the None key), the RenamingPlan will
        # have failed.
        self.failures = {
            control : []
            for control, _ in CONTROLLABLES.values()
        }
        self.failures[None] = []

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
    # renaming can occur. The method does not raise; rather, when failures
    # occur, they are stored in self.failures based on their type and whether
    # the user has configured the RenamingPlan to handle failures of that kind.
    #
    ####

    def prepare(self):
        # Don't prepare more than once.
        if self.has_prepared:
            return
        else:
            self.has_prepared = True

        # Get the input paths and parse them to get RenamePair instances.
        result = self.catch_failure(self.parse_inputs())
        if self.failed:
            return
        else:
            self.rps = result

        # Create the renaming and filtering functions from
        # user-supplied code, if any was given.
        for action in ('filter', 'rename'):
            result = self.catch_failure(self.make_user_defined_func(action))
            if self.failed:
                return
            else:
                setattr(self, f'{action}_func', result)

        # Run various steps that process the RenamePair instances individually:
        # filtering, computing new paths, or validating.
        #
        # We use the processed_rps() method to execute the step, handle
        # failures appropriately, and yield a potentially filtered collection
        # of potentially modified RenamePair instances.
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

            # Register failure if the step & failure-control filtered out everything.
            if not self.rps:
                f = NoPathsFailure(FAIL.no_paths_after_processing)
                self.catch_failure(f)

            # Stop if the plan has failed either directly or via filtering.
            if self.failed:
                return

    ####
    # Parsing inputs to obtain the original and, in some cases, new paths.
    ####

    def parse_inputs(self):
        # If we have rename_code, inputs are just original paths.
        if self.rename_code:
            rps = tuple(
                RenamePair(orig, None)
                for orig in self.inputs
                if orig
            )
            return rps if rps else ParseFailure(FAIL.no_input_paths)

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
                return ParseFailure(FAIL.parsing_paragraphs)
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
                        return ParseFailure(FAIL.parsing_row.format(row = row))
        else:
            # Flat: like paragraphs without the blank-line delimiter.
            paths = [line for line in self.inputs if line]
            i = len(paths) // 2
            origs, news = (paths[0:i], paths[i:])

        # Fail if we got unqual numbers of original vs new paths, or no paths at all.
        if len(origs) != len(news):
            return ParseFailure(FAIL.parsing_inequality)
        elif not origs:
            return ParseFailure(FAIL.no_input_paths)

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
            return UserCodeExecFailure(msg)

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
            #   - failure: set if the instance failed a validation check.
            #   - exclude: set true if user's filtering code rejected the instance.
            #   - create_parent: can be set here if a controlled failure occurred.
            #   - clobber: ditto.
            #
            rp = step(rp, next(seq))

            # Check whether the RenamePair has a failure and act accordingly.
            control = self.catch_failure(rp, control_mode = True)
            if control == CONTROLS.skip:
                # Skip RenamePair because a failure occured, but proceed with others.
                pass
            elif control == CONTROLS.keep:
                # Retain the RenamePair even though a failure occured during filtering.
                yield clone(rp, failure = None)
            elif control == CONTROLS.create:
                # The RenamePair lacks a parent, but we will create it before renaming.
                yield clone(rp, create_parent = True, failure = None)
            elif control == CONTROLS.clobber:
                # During renaming, the RenamePair will overwrite something.
                yield clone(rp, clobber = True, failure = None)
            elif rp.exclude:
                # The user's code decided to filter out the RenamePair.
                pass
            else:
                # No failure and not filtered out.
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
                msg = FAIL.filter_code_invalid.format(e, rp.orig)
                return clone(rp, failure = RpFilterFailure(msg))
        else:
            return rp

    def execute_user_rename(self, rp, seq_val):
        if self.rename_code:
            # Compute the new path.
            try:
                new = self.rename_func(rp.orig, Path(rp.orig), seq_val, self)
            except Exception as e:
                msg = FAIL.rename_code_invalid.format(e, rp.orig)
                return clone(rp, failure = RpRenameFailure(msg))
            # Validate its type and return a modified RenamePair instance.
            if isinstance(new, (str, Path)):
                return clone(rp, new = str(new))
            else:
                typ = type(new).__name__
                msg = FAIL.rename_code_bad_return.format(typ, rp.orig)
                return clone(rp, failure = RpRenameFailure(msg))
        else:
            return rp

    def check_orig_exists(self, rp, seq_val):
        if self.path_exists(rp.orig):
            return rp
        else:
            return clone(rp, failure = RpMissingFailure(FAIL.orig_missing))

    def check_orig_new_differ(self, rp, seq_val):
        if rp.equal:
            return clone(rp, failure = RpEqualFailure(FAIL.orig_new_same))
        else:
            return rp

    def check_new_not_exists(self, rp, seq_val):
        # The failure is conditional on ORIG and NEW being different
        # to avoid pointless reporting of multiple failures in such cases.
        if self.path_exists(rp.new) and not rp.equal:
            return clone(rp, failure = RpExistsFailure(FAIL.new_exists))
        else:
            return rp

    def check_new_parent_exists(self, rp, seq_val):
        if self.path_exists(str(Path(rp.new).parent)):
            return rp
        else:
            return clone(rp, failure = RpMissingParentFailure(FAIL.new_parent_missing))

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
            return clone(rp, failure = RpCollsionFailure(FAIL.new_collision))

    ####
    # Methods related to failure control.
    ####

    def catch_failure(self, x, control_mode = False):
        # Used as a helper when calling other methods to:
        # - Examine an object X to see if it is/has a Failure.
        # - If so, store the Failure.
        # - Return either X or the failure-control mechanism.

        # Get the Failure, if any.
        if isinstance(x, Failure):
            f = x
        elif isinstance(x, RenamePair):
            f = x.failure
        else:
            f = None

        # Track it and determine its failure-control mechanism, if any.
        if f:
            control = self.fail_config.get(type(f), None)
            self.failures[control].append(f)
        else:
            control = None

        # Return initial object or the control.
        return control if control_mode else x

    @property
    def failed(self):
        # The RenamingPlan has failed if there are any uncontrolled failures.
        return bool(self.uncontrolled_failures)

    @property
    def uncontrolled_failures(self):
        return self.failures[None]

    @property
    def first_failure(self):
        fs = self.uncontrolled_failures
        return fs[0] if fs else None

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
            return {
                path : self.DEFAULT_FILE_SYS_VAL
                for path in file_sys
            }

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
            raise BmvError(FAIL.rename_done_already)
        else:
            self.has_renamed = True

        # Ensure than we have prepare, and raise it failed.
        self.prepare()
        if self.failed:
            raise BmvError(FAIL.prepare_failed, failures = self.failures[None])

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
            # Failure controls.
            skip_equal = self.skip_equal,
            skip_missing = self.skip_missing,
            skip_missing_parent = self.skip_missing_parent,
            create_missing_parent = self.create_missing_parent,
            skip_existing_new = self.skip_existing_new,
            clobber_existing_new = self.clobber_existing_new,
            skip_colliding_new = self.skip_colliding_new,
            clobber_colliding_new = self.clobber_colliding_new,
            skip_failed_rename = self.skip_failed_rename,
            skip_failed_filter = self.skip_failed_filter,
            keep_failed_filter = self.keep_failed_filter,
            # Other.
            failures = self.failures,
            prefix_len = self.prefix_len,
            rename_pairs = [asdict(rp) for rp in self.rps],
        )

def validated_failure_controls(x, opts_mode = False):
    # Takes either the parsed command-line options (opts) or a RenamingPlan
    # instance. Processes the failure-control attributes of that object.
    #
    # Builds a dict mapping each Failure class that the user wants to control
    # to a (CONTROL, NAME) tuple.
    #
    # Returns that dict (opts_mode = True), a simplified version of it (False),
    # or an OptsFailure (in the case of contradictory configurations by
    # the user).

    # Converts a name to an option: eg, 'skip_equal' to '--skip-equal'.
    name_to_opt = lambda nm: CON.dash + nm.replace(CON.underscore, CON.hyphen)

    # Build the failure-control dict.
    config = {}
    for name2, (control, fail_cls) in CONTROLLABLES:
        # If X has a true value for the attribute, we need to deal with it.
        if getattr(x, name2, None):
            if fail_cls in config:
                # If the failure-class is already in the failure-control
                # dict, the user has attempted to set two different
                # controls for the same failure type. Return an OptsFailure.
                (_, name1) = config[fail_cls]
                if opts_mode:
                    name1, name2 = (name_to_opt(name1), name_to_opt(name2))
                msg = FAIL.conflicting_controls.format(name1, name2)
                return OptsFailure(msg)
            else:
                # No problem: add an entry to the dict.
                config[fail_cls] = (control, name2)

    # Return the dict or a simplified variant of it.
    if opts_mode:
        return x
    else:
        d = {
            fail_cls : control
            for fail_cls, (control, name) in config.items()
        }
        return d

