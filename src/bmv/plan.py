
import re
import sys

from itertools import groupby
from pathlib import Path
from dataclasses import replace

from .constants import (
    CON,
    FAIL,
    FAIL_NAMES,
    FAIL_CONTROLS as FC,
)
from .data_objects import (
    RenamePair,
    Failure,
    OptsFailure,
    ParseFailure,
    RenameFailure,
    FilterFailure,
    RenamePairFailure,
    ExitCondition,
)

class RenamingPlan:

    # Mapping from the user-facing failure names to their:
    # (1) Failure type, and (2) supported failure-control mechanisms.
    #
    #   None   : Failure is not controlled, so the RenamingPlan will fail.
    #   skip   : The affected RenamePair will be skipped.
    #   keep   : The affected RenamePair will be kept [rather than filtered out].
    #   create : The missing path will be created [parent of RenamePair.new].
    #   clobber: The affected path will be clobbered [existing or colliding RenamePair.new].
    #
    SUPPORTED_CONTROLS = {
        # FAIL_NAMES                Failure type             Supported FAILURE_CONTROLS.
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
        # etc) to the failures that were controlled by the mechanism. If the
        # dict ends up having any uncontrollec failures (under the None key),
        # the RenamingPlan will have failed.
        self.failures = {control : [] for control in FC}
        self.failures[None] = []

        # Other stuff.
        self.prefix_len = 0

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

        # Filter the paths.
        if self.filter_code:
            seq = self.compute_sequence_iterator()
            filters = []
            for rp in self.rps:
                seq_val = next(seq)
                result = self.execute_user_filter_code(filter_func, rp.orig, seq_val)
                # ok, fail, skip
                if isinstance(result, Failure):
                    self.failures.append(result)
                    return
                else:
                    filters.append(bool(result))
            self.rps = tuple(
                rp
                for rp, keep in zip(self.rps, filters)
                if keep
            )

        # Generate new paths.
        if self.rename_code:
            seq = self.compute_sequence_iterator()
            for rp in self.rps:
                seq_val = next(seq)
                result = self.execute_user_rename_code(rename_func, rp.orig, seq_val)
                # ok, fail, skip
                if isinstance(result, Failure):
                    self.failures.append(result)
                    return
                else:
                    rp.new = result

        rp_steps = (
            self.execute_user_filter,
            self.execute_user_rename,
            self.check_orig_exists,
            self.check_orig_new_differ,
            self.check_new_not_exists,
            self.check_new_parent_exists,
            self.check_new_collisions,
        )

        for step in rp_steps:
            self.rps = tuple(self.processed_rps(step))
            if not self.rps:
                f = NoPathsFailure(FAIL.no_paths_after_processing)
                self.catch_failure(f)
            if self.failed:
                break

        def processed_rps(self, step):
            for rp in self.rps:
                ok, control = self.catch_failure(step(rp))
                if control == FC.skip:
                    pass
                elif control == FC.keep:
                    yield rp
                elif control == FC.create:
                    yield replace(rp, create_parent = True)
                elif control == FC.clobber:
                    yield replace(rp, clobber = True)
                else:
                    yield rp

        def execute_user_func(self, executor, func):
            seq = self.compute_sequence_iterator()
            return tuple(
                executor(func, rp.orig, next(seq))
                for rp in self.rps
            )

    def parse_inputs(self):
        # If we have rename_code, inputs are just original paths.
        if self.rename_code:
            rps = tuple(
                RenamePair(orig, None)
                for orig in self.inputs
                if orig
            )
            return rps if rps else return ParseFailure(FAIL.no_input_paths)

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

    def strip_prefix(self, orig):
        i = self.prefix_len
        return orig[i:] if i else orig

    def compute_prefix_len(self):
        origs = tuple(rp.orig for rp in self.rps)
        self.prefix_len = len(commonprefix(origs))

    def compute_sequence_iterator(self):
        return iter(range(self.seq_start, sys.maxsize, self.seq_step))

    def execute_user_filter_code(self, func, orig, seq_val):
        # Run the user-supplied filtering code.
        try:
            return bool(func(orig, Path(orig), seq_val, self))
        except Exception as e:
            msg = f'Error in user-supplied filtering code: {e} [original path: {orig}]'
            return FilterFailure(msg)

    def execute_user_rename_code(self, func, orig, seq_val):
        # Run the user-supplied code to get the new path.
        try:
            new = func(orig, Path(orig), seq_val, self)
        except Exception as e:
            msg = f'Error in user-supplied renaming code: {e} [original path: {orig}]'
            return RenameFailure(msg)

        # Validate its type and return.
        if isinstance(new, str):
            return new
        elif isinstance(new, Path):
            return str(new)
        else:
            typ = type(new).__name__
            msg = f'Invalid type from user-supplied renaming code: {typ} [original path: {orig}]'
            return RenameFailure(msg)

    def validate_rename_pairs(self):
        if not self.rps:
            self.failures.append(NoPathsFailure(FAIL.no_paths))

        # Organize rps into dict-of-list, keyed by new.
        grouped_by_new = {}
        for rp in self.rps:
            grouped_by_new.setdefault(str(rp.new), []).append(rp)

        # Original paths should exist.
        self.failures.extend(
            RenamePairFailure(FAIL.orig_missing, rp)
            for rp in self.rps
            if not self.path_exists(Path(rp.orig))
        )

        # New paths should not exist.
        # The failure is conditional on ORIG and NEW being different
        # to avoid pointless reporting of multiple failures in such cases.
        self.failures.extend(
            RenamePairFailure(FAIL.new_exists, rp)
            for rp in self.rps
            if self.path_exists(Path(rp.new)) and not rp.equal
        )

        # Parent of new path should exist.
        self.failures.extend(
            RenamePairFailure(FAIL.new_parent_missing, rp)
            for rp in self.rps
            if not self.path_exists(Path(rp.new).parent)
        )

        # Original path and new path should differ.
        self.failures.extend(
            RenamePairFailure(FAIL.orig_new_same, rp)
            for rp in self.rps
            if rp.equal
        )

        # New paths should not collide among themselves.
        self.failures.extend(
            RenamePairFailure(FAIL.new_collision, rp)
            for group in grouped_by_new.values()
            for rp in group
            if len(group) > 1
        )


    def path_exists(self, p):
        if self.file_sys is None:
            # Check the real file system.
            return p.exists()
        else:
            # Or check a fake file system added for testing purposes.
            return p in self.file_sys

    def catch_failure(self, x):
        # Used when calling other methods to (1) catch a Failure instance, (2)
        # store it in self.failures under the appropriate failure-control key,
        # and (3) forward the value along with the control in a 2-tuple.
        if isinstance(x, Failure):
            control = self.fail_config.get(failure, None)
            self.failures.append(x)
            return (x, control)
        else:
            return (x, None)

    @property
    def failed(self):
        # The RenamingPlan has failed if there are any uncontrolled failures.
        return bool(self.failures[None])

