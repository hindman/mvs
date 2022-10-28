
import re
import sys

from itertools import groupby
from pathlib import Path

from .constants import (
    CON,
    FAIL,
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

    def __init__(self,
                 inputs,
                 rename_code,
                 structure = None,
                 seq_start = 1,
                 seq_step = 1,
                 skip_equal = False,
                 filter_code = None,
                 indent = 4,
                 file_sys = None):

        # Add validation. Convert to attrs.
        self.inputs = tuple(inputs)
        self.rename_code = rename_code
        self.structure = structure
        self.seq_start = seq_start
        self.seq_step = seq_step
        self.skip_equal = skip_equal
        self.filter_code = filter_code
        self.indent = indent
        self.file_sys = file_sys

        # Other stuff.
        self.prefix_len = 0
        self.failures = []

    @property
    def failed(self):
        return bool(self.failures)

    def prepare(self):
        # parsing:
        #   1 ParseFailure
        #   fatal
        #
        # create user functions:
        #   1 filtering
        #   1 renaming
        #   fatal
        #
        # execute user code:
        #   N FilterFailure
        #   skip-failed-filter [not compelling]
        #
        #   N RenameFailure
        #   skip-failed-rename [not compelling]
        #
        # validation:
        #
        #   holistic checks:
        #       1 NoPathsFailure
        #       noop
        #
        #       N* RenamePairFailure: new paths should not collide among themselves
        #       allow-new-collision
        #
        #   individual rp checks:
        #       N RenamePairFailure: orig should exist
        #       skip-missing-orig [not compelling]
        #
        #       N RenamePairFailure: new should not exist
        #       allow-clobber
        #
        #       N RenamePairFailure: parent of new should exist
        #       create-new-parent
        #
        #       N RenamePairFailure: new and orig should differ
        #       skip-equal

        # Get the input paths and parse them to get RenamePair instances.
        self.rps = self.catch_failure(self.parse_inputs())
        if self.failed:
            return

        # # Get the input paths and parse them to get RenamePair instances.
        # result = self.parse_inputs()
        # if isinstance(result, Failure):
        #     self.failures.append(result)
        #     return
        # else:
        #     self.rps = result

        # Create filtering function from user code.
        if self.filter_code:
            # TODO: need to return UserCodeFailure.
            filter_func = self.catch_failure(self.make_user_defined_func('filter'))
            if self.failed:
                return

        # Create renaming function from user code.
        if self.rename_code:
            # TODO: need to return UserCodeFailure.
            rename_func = self.catch_failure(self.make_user_defined_func('rename'))
            if self.failed:
                return

        # Filter the paths.
        if self.filter_code:
            seq = self.compute_sequence_iterator()
            filters = []
            for rp in self.rps:
                seq_val = next(seq)
                result = self.execute_user_filter_code(filter_func, rp.orig, seq_val)
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

            # filters = self.execute_user_func(self.execute_user_filter_code, filter_func)
            # retained = []
            # for rp, f in zip(self.rps, filters):
            #     if isinstance(f, Failure):
            #         if self.skip_failed_filter:
            #             pass
            #         else:
            #             self.failures.append(f)
            #     else:
            #         if f:
            #             retained.append(rp)
            #         else:
            #             pass
            # self.rps = tuple(retained)

        # Generate new paths.
        if self.rename_code:
            seq = self.compute_sequence_iterator()
            for rp in self.rps:
                seq_val = next(seq)
                result = self.execute_user_rename_code(rename_func, rp.orig, seq_val)
                if isinstance(result, Failure):
                    self.failures.append(result)
                    return
                else:
                    rp.new = result

        def execute_user_func(self, executor, func):
            seq = self.compute_sequence_iterator()
            return tuple(
                executor(func, rp.orig, next(seq))
                for rp in self.rps
            )

        # # If user supplied filtering code, use it to filter the paths.
        # if self.filter_code:
        #     # This call could fail.
        #     func = self.make_user_defined_func('filter', self.filter_code)
        #     seq = self.compute_sequence_iterator()
        #     filters = []
        #     for rp in self.rps:
        #         seq_val = next(seq)
        #         result = self.execute_user_filter_code(func, rp.orig, seq_val)
        #         if isinstance(result, Failure):
        #             self.failures.append(result)
        #             return
        #         else:
        #             filters.append(bool(result))
        #     self.rps = tuple(
        #         rp
        #         for rp, keep in zip(self.rps, filters)
        #         if keep
        #     )

        # # If user supplied renaming code, use it to generate new paths.
        # if self.rename_code:
        #     func = self.make_user_defined_func('rename', self.rename_code)
        #     seq = self.compute_sequence_iterator()
        #     for rp in self.rps:
        #         seq_val = next(seq)
        #         result = self.execute_user_rename_code(func, rp.orig, seq_val)
        #         if isinstance(result, Failure):
        #             self.failures.append(result)
        #             return
        #         else:
        #             rp.new = result

        # Skip RenamePair instances with equal paths.
        if self.skip_equal:
            self.rps = [rp for rp in self.rps if rp.orig != rp.new]

        # Validate the renaming plan.
        self.validate_rename_pairs()

    def parse_inputs(self):
        # If we have rename_code, inputs are just original paths.
        if self.rename_code:
            return tuple(
                RenamePair(orig, None)
                for orig in self.inputs
                if orig
            )

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

        # Stop if we got unqual numbers of paths.
        if len(origs) != len(news):
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
        exec(code, globs, locs)
        return locs[func_name]

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
            return p.exists()
        else:
            return p in self.file_sys

    def catch_failure(self, x):
        if isinstance(x, Failure):
            self.failures.append(x)
        return x

