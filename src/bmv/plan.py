import re
import sys

from dataclasses import replace as clone
from itertools import groupby
from os.path import commonprefix
from pathlib import Path

from .constants import (
    CON,
    FAIL,
    FAIL_NAMES,
    FAIL_CONTROLS as FC,
    STRUCTURES,
)
from .data_objects import (
    RenamePair,
    Failure,
    ParseFailure,
    UserCodeExecFailure,
    NoPathsFailure,
    RpFilterFailure,
    RpRenameFailure,
    RpEqualFailure,
    RpMissingFailure,
    RpMissingParentFailure,
    RpExistsFailure,
    RpCollsionFailure,
)

class RenamingPlan:

    # Mapping from the user-facing failure names to their:
    # (1) Failure type, and (2) supported failure-control mechanisms.
    #
    #   skip   : The affected RenamePair will be skipped.
    #   keep   : The affected RenamePair will be kept [rather than filtered out].
    #   create : The missing path will be created [parent of RenamePair.new].
    #   clobber: The affected path will be clobbered [existing or colliding RenamePair.new].
    #
    SUPPORTED_CONTROLS = {
        FAIL_NAMES.filter_error   : (RpFilterFailure,        (FC.skip, FC.keep)),
        FAIL_NAMES.rename_error   : (RpRenameFailure,        (FC.skip,)),
        FAIL_NAMES.equal          : (RpEqualFailure,         (FC.skip,)),
        FAIL_NAMES.missing        : (RpMissingFailure,       (FC.skip,)),
        FAIL_NAMES.missing_parent : (RpMissingParentFailure, (FC.skip, FC.create)),
        FAIL_NAMES.existing_new   : (RpExistsFailure,        (FC.skip, FC.clobber)),
        FAIL_NAMES.colliding_new  : (RpCollsionFailure,      (FC.skip, FC.clobber)),
    }

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
                 skip = None,
                 keep = None,
                 create = None,
                 clobber = None,
                 ):

        # Add validation. Convert to attrs.
        self.inputs = tuple(inputs)
        self.structure = structure
        self.rename_code = rename_code
        self.filter_code = filter_code
        self.indent = indent
        self.seq_start = seq_start
        self.seq_step = seq_step
        self.file_sys = file_sys

        # In fail_config, we get a dict mapping each controlled Failure type
        # to the user's requested control mechanism (skip, keep, create, clobber).
        # This call validates and builds the dict.
        self.fail_config = self.build_failure_control_config({
            FC.skip: skip,
            FC.keep: keep,
            FC.create: create,
            FC.clobber: clobber,
        })

        # The failures dict stores all failures that occurred during the
        # prepare() phase. A failure can be either controlled (as requested by
        # the user) or not. The dict maps each control mechanism (skip, keep,
        # create, clobber) to the failures that were controlled by the
        # mechanism. If the dict ends up having any uncontrollec failures
        # (under the None key), the RenamingPlan will have failed.
        self.failures = {control : [] for control in FC}
        self.failures[None] = []

        # Other stuff.
        self.prefix_len = 0

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
        # Get the input paths and parse them to get RenamePair instances.
        self.rps, _ = self.catch_failure(self.parse_inputs())
        if self.failed:
            return

        # Create filtering function from user code.
        if self.filter_code:
            self.filter_func, _ = self.catch_failure(self.make_user_defined_func('filter'))
            if self.failed:
                return

        # Create renaming function from user code.
        if self.rename_code:
            self.rename_func, _ = self.catch_failure(self.make_user_defined_func('rename'))
            if self.failed:
                return

        # Run various steps that process the RenamePair instances individually:
        # filtering, computing new paths, or validating.
        #
        # We use the processed_rps() method to execute the step, handle
        # failures appropriately, and yield a potentially filtered collection
        # of potentially modified RenamePair instances.
        #
        # Since filtering can occur at each step (depending on failure-control
        # settings) we check for NoPathsFailure after each step.
        #
        rp_steps = (
            self.execute_user_filter,
            self.execute_user_rename,
            self.check_orig_exists,
            self.check_orig_new_differ,
            self.check_new_not_exists,
            self.check_new_parent_exists,
        )
        for step in rp_steps:
            self.rps = tuple(self.processed_rps(step))
            if not self.rps:
                f = NoPathsFailure(FAIL.no_paths_after_processing)
                self.catch_failure(f)
            if self.failed:
                break

        self.check_new_collisions()
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
        elif self.structure == STRUCTURES.flat:
            # Flat: like paragraphs without the blank-line delimiter.
            paths = [line for line in self.inputs if line]
            i = len(paths) // 2
            origs, news = (paths[0:i], paths[i:])
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
                    cells = row.split(CON.tab)
                    if len(cells) == 2:
                        origs.append(cells[0])
                        news.append(cells[1])
                    else:
                        return ParseFailure(FAIL.parsing_row.format(row = row))
        else:
            return ParseFailure(FAIL.parsing_opts)

        # Fail if we got no paths or unqual numbers of original vs new paths.
        if not origs:
            return ParseFailure(FAIL.no_input_paths)
        elif len(origs) != len(news):
            return ParseFailure(FAIL.parsing_inequality)

        # Return the RenamePair instances.
        return tuple(
            RenamePair(orig, new)
            for orig, new in zip(origs, news)
        )

    ####
    # Creating the user-defined functions for filtering and renaming.
    ####

    def make_user_defined_func(self, action):
        # Define the text of the code.
        func_name = f'do_{action}'
        code = CON.user_code_fmt.format(
            func_name = func_name,
            user_code = getattr(self, f'{action}_code'),
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
            msg = f''
            return UserCodeExecFailure(msg)

    ####
    # A method to execute the steps that process RenamePair instance individually.
    ####

    def processed_rps(self, step):
        self.prefix_len = self.compute_prefix_len()
        seq = self.compute_sequence_iterator()
        for rp in self.rps:
            # The step() call can return one of three types of values:
            #
            # (1) A RenamePairFailure instance if there was a failure.
            # In these cases, catch_failure() will determine the
            # failure-control value, and we will act accordingly here.
            #
            # (2) A RenamePair instance. It might be the same as the
            # current rp here (eg, in the case of checks that simply determine
            # whether the rp is valid), or it might be a modified instance
            # (eg, in the case of the step to compute the new path).
            #
            # (3) None, if the RenamePair should be skipped. This occurs
            # if the filtering code ran successfully (ie no Failure) but
            # it determined that the RenamePair should be filtered out.
            #
            result, control = self.catch_failure(step(rp, next(seq)))
            if control == FC.skip:
                pass
            elif control == FC.keep:
                yield rp
            elif control == FC.create:
                yield clone(rp, create_parent = True)
            elif control == FC.clobber:
                yield clone(rp, clobber = True)
            elif result is None:
                pass
            else:
                yield result

    ####
    # The steps that process RenamePair instance individually.
    ####

    def execute_user_filter(self, rp, seq_val):
        if self.filter_code:
            try:
                result = self.filter_func(rp.orig, Path(rp.orig), seq_val, self)
                return rp if result else None
            except Exception as e:
                msg = f'Error in user-supplied filtering code: {e} [original path: {rp.orig}]'
                return RpFilterFailure(msg, rp)
        else:
            return rp

    def execute_user_rename(self, rp, seq_val):
        if self.rename_code:
            # Compute the new path.
            try:
                new = self.rename_func(rp.orig, Path(rp.orig), seq_val, self)
            except Exception as e:
                msg = f'Error in user-supplied renaming code: {e} [original path: {rp.orig}]'
                return RpRenameFailure(msg, rp)
            # Validate its type and return a modified RenamePair instance.
            if isinstance(new, (str, Path)):
                return clone(rp, new = str(new))
            else:
                typ = type(new).__name__
                msg = f'Invalid type from user-supplied renaming code: {typ} [original path: {rp.orig}]'
                return RpRenameFailure(msg, rp)
        else:
            return rp

    def check_orig_exists(self, rp, seq_val):
        if self.path_exists(Path(rp.orig)):
            return rp
        else:
            return RpMissingFailure(FAIL.orig_missing, rp)

    def check_orig_new_differ(self, rp, seq_val):
        if rp.equal:
            return RpEqualFailure(FAIL.orig_new_same, rp)
        else:
            return rp

    def check_new_not_exists(self, rp, seq_val):
        # The failure is conditional on ORIG and NEW being different
        # to avoid pointless reporting of multiple failures in such cases.
        if self.path_exists(rp.new) and not rp.equal:
            return RpExistsFailure(FAIL.new_exists, rp)
        else:
            return rp

    def check_new_parent_exists(self, rp, seq_val):
        if self.path_exists(Path(rp.new).parent):
            return rp
        else:
            return RpMissingParentFailure(FAIL.new_parent_missing, rp)

    def check_new_collisions(self):
        # Organize rps into dict-of-list, keyed by the new path.
        groups = {}
        for rp in self.rps:
            groups.setdefault(rp.new, []).append(rp)
        # If any group contains multiple members, add them all as potential failures.
        for g in groups.values():
            if len(g) > 1:
                for rp in g:
                    f = RpCollsionFailure(FAIL.new_collision, rp)
                    self.catch_failure(f)

    ####
    # Methods related to failure control.
    ####

    def build_failure_control_config(self, config):
        fc = {}
        for control, failure_names in config.items():
            for fnm in (failure_names or []):
                ftype, supported = self.SUPPORTED_CONTROLS.get(fnm, (None, []))
                if control in supported:
                    fc[ftype] = control
                else:
                    msg = f'RenamingPlan received an invalid failure-control: {control} {fnm}'
                    raise ValueError(msg)
        return fc

    def catch_failure(self, x):
        # Used when calling other methods to (1) catch a Failure instance, (2)
        # store it in self.failures under the appropriate failure-control key,
        # and (3) forward the value along with the control in a 2-tuple.
        if isinstance(x, Failure):
            control = self.fail_config.get(failure, None)
            self.failures[control].append(x)
            return (x, control)
        else:
            return (x, None)

    @property
    def failed(self):
        # The RenamingPlan has failed if there are any uncontrolled failures.
        return bool(self.failures[None])

    ####
    # Utilities.
    ####

    def compute_sequence_iterator(self):
        return iter(range(self.seq_start, sys.maxsize, self.seq_step))

    def compute_prefix_len(self):
        origs = tuple(rp.orig for rp in self.rps)
        return len(commonprefix(origs))

    def strip_prefix(self, orig):
        i = self.prefix_len
        return orig[i:] if i else orig

    def path_exists(self, p):
        if self.file_sys is None:
            # Check the real file system.
            return Path(p).exists()
        else:
            # Or check a fake file system added for testing purposes.
            return p in self.file_sys

