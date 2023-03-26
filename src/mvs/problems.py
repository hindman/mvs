from dataclasses import dataclass, field
from short_con import constants, cons

from .utils import (
    CON,
    MSG_FORMATS as MF,
    MvsError,
    RenamePair,
    seq_or_str,
    underscores_to_hyphens,
)

####
# Problem names and associated messages/formats.
#
# See command-line help text for more details on problems and their control.
####

PROBLEM_NAMES = PN = constants('ProblemNames', (
    # Controllable.
    'equal',
    'same',
    'recase',
    'missing',
    'type',
    'parent',
    'existing',
    'colliding',
    'existing_diff',
    'colliding_diff',
    'existing_non_empty',
    # Not controllable.
    'all_filtered',
    'parsing_no_paths',
    'parsing_paragraphs',
    'parsing_row',
    'parsing_imbalance',
    'user_code_exec',
    'filter_code_invalid',
    'rename_code_invalid',
    'rename_code_bad_return',
))

PROBLEM_FORMATS = constants('ProblemFormats', {
    # Controllable.
    PN.equal:                  'Original path and new path are the exactly equal',
    PN.same:                   'Original path and new path are the functionally the same',
    PN.recase:                 'User inputs requested path name case change, but file system already agrees with new',
    PN.missing:                'Original path does not exist',
    PN.type:                   'Original path must be regular file or directory',
    PN.parent:                 'Parent directory of new path does not exist',
    PN.existing:               'New path exists',
    PN.colliding:              'New path collides with another new path',
    PN.existing_diff:          'New path exists and differs with original in type',
    PN.colliding_diff:         'New path collides with another new path, and they differ in type',
    PN.existing_non_empty:     'New path collides with a non-empty directory',
    # Not controllable.
    PN.all_filtered:           'All paths were filtered out during processing',
    PN.parsing_no_paths:       'No input paths',
    PN.parsing_paragraphs:     'The --paragraphs option expects exactly two paragraphs',
    PN.parsing_row:            'The --rows option expects rows with exactly two cells: {!r}',
    PN.parsing_imbalance:      'Got an unequal number of original paths and new paths',
    PN.user_code_exec:         '{}',
    PN.filter_code_invalid:    'Error in user-supplied filtering code: {} [original path: {}]',
    PN.rename_code_invalid:    'Error in user-supplied renaming code: {} [original path: {}]',
    PN.rename_code_bad_return: 'Invalid type from user-supplied renaming code: {} [original path: {}]',
})

####
# Data object to represent a problem.
####

@dataclass(init = False, frozen = True)
class Problem:
    name: str
    msg: str
    rp : RenamePair = None

    def __init__(self, name, *xs, msg = None, rp = None):
        # Custom initializer, because we need a convenience lookup to build
        # the ultimate message, given a problem name and arguments.
        # To keep Problem instances frozen, we modify __dict__ directly.
        d = self.__dict__
        d['name'] = name
        d['msg'] = msg or self.format_for(name).format(*xs)
        d['rp'] = rp

    @property
    def formatted(self):
        if self.rp is None:
            return self.msg
        else:
            return f'{self.msg}:\n{self.rp.formatted}'

    @staticmethod
    def format_for(name):
        return PROBLEM_FORMATS[name]

####
# Problem controls.
####

CONTROLS = C = constants('Controls', (
    'halt',     # Halt RenamingPlan before any renaming occurs.
    'skip',     # Skip affected RenamePair (rp).
    'clobber',  # Delete rp.new before renaming old-to-new.
    'create',   # Create missing parent of rp.new before renaming old-to-new.
))

class ProblemControl:

    # A dict defining the valid controls for each Problem name.
    # The first control in each tuple is the default.
    # Values in comments could be allowed in the future.
    VALID_CONTROLS = {
        PN.equal:                  (C.skip, C.halt),
        PN.same:                   (C.skip, C.halt),
        PN.recase:                 (C.skip, C.halt),
        PN.missing:                (C.skip, C.halt),
        PN.type:                   (C.skip, C.halt),
        PN.parent:                 (C.skip, C.halt, C.create),
        PN.existing:               (C.skip, C.halt, C.clobber),
        PN.colliding:              (C.skip, C.halt, C.clobber),
        PN.existing_diff:          (C.skip, C.halt),  # C.clobber
        PN.colliding_diff:         (C.skip, C.halt),  # C.clobber
        PN.existing_non_empty:     (C.skip, C.halt),  # C.clobber
        PN.filter_code_invalid:    (C.halt,),         # C.skip
        PN.rename_code_invalid:    (C.halt,),         # C.skip
        PN.rename_code_bad_return: (C.halt,),         # C.skip
        PN.all_filtered:           (C.halt,),
        PN.parsing_no_paths:       (C.halt,),
        PN.parsing_paragraphs:     (C.halt,),
        PN.parsing_row:            (C.halt,),
        PN.parsing_imbalance:      (C.halt,),
        PN.user_code_exec:         (C.halt,),
    }

    # A dict mapping each ProblemControl names to its
    # corresponding (PROBLEM_NAME, CONTROL_NAME) tuple.
    LOOKUP_BY_NAME = {
        underscores_to_hyphens(f'{c}-{prob}') : (prob, c)
        for prob, controls in VALID_CONTROLS.items()
        for c in controls
    }

    # ProblemControl names: all of them.
    ALL_NAMES = tuple(LOOKUP_BY_NAME)

    # ProblemControl names: just the defaults.
    DEFAULTS = {
        underscores_to_hyphens(f'{controls[0]}-{prob}')
        for prob, controls in VALID_CONTROLS.items()
    }

    def __init__(self, raw_name):
        self.name = underscores_to_hyphens(raw_name)
        tup = self.LOOKUP_BY_NAME.get(self.name, None)
        if tup:
            self.prob = tup[0]
            self.control = tup[1]
        else:
            msg = MF.invalid_control.format(raw_name)
            raise MvsError(msg)

    @classmethod
    def merge(cls, *batches, want_map = False):
        # Takes ProblemControl names from one or more sources. For example,
        # (1) controls from user-prefs and command-line options, or
        # (2) defaults controls and controls given to RenamingPlan.
        #
        # Each batch of names can be a sequence of strings or
        # a space-delimited string.
        #
        # Standardizes and validates the names in each batch. Within each
        # batch, the user should not try to control the same problem in
        # different ways.
        #
        # Merges the controls from different batches together. Controls from
        # later batches trump those from earlier ones.
        #
        # Returns the merged data either as a tuple of ProblemControl
        # names or as a dict mapping each problem name to its
        # desired control mechanism.

        # Convert each batch into a validated dict
        # mapping problem name to desired control.
        validated = []
        for b in batches:
            d = {}
            pc_names = seq_or_str(b)
            for name in pc_names:
                pc = cls(name)
                prob = pc.prob
                if prob in d and d[prob] != pc.control:
                    fmt = MF.conflicting_controls
                    msg = fmt.format(prob, d[prob], pc.control)
                    raise MvsError(msg)
                else:
                    d[prob] = pc.control
            validated.append(d)

        # Merge those dicts, giving highest precedence to later batches.
        merged = {}
        for d in validated:
            merged.update(d)

        # Return the merged data.
        if want_map:
            return merged
        else:
            return tuple(
                f'{control}-{prob}'
                for prob, control in merged.items()
            )

