from dataclasses import dataclass, field
from short_con import constants, cons

from .utils import (
    MSG_FORMATS as MF,
    MvsError,
    seq_or_str,
    underscores_to_hyphens,
    with_newline,
)

####
# Problems and Failures.
#
# Problems are specific to one RenamePair and they are handled
# via problem controls: halt, skip, create, clobber.
#
# Failures are not specific to a single RenamePair and/or have
# no meaningful control mechanism. Most relate to bad inputs.
#
# See command-line help text for more details on problems and their control.
####

PROBLEM_NAMES = PN = constants('ProblemNames', (
    'equal',
    'same',
    'recase',
    'missing',
    'type',
    'parent',
    'exists',
    'collides',
    'exists_diff',
    'collides_diff',
    'exists_full',
    'filter',
    'rename',
))

PROBLEM_FORMATS = constants('ProblemFormats', {
    PN.equal:         'Original path and new path are the exactly equal',
    PN.same:          'Original path and new path are the functionally the same',
    PN.recase:        'User inputs requested path name case change, but file system already agrees with new',
    PN.missing:       'Original path does not exist',
    PN.type:          'Original path must be regular file or directory',
    PN.parent:        'Parent directory of new path does not exist',
    PN.exists:        'New path exists',
    PN.collides:      'New path collides with another new path',
    PN.exists_diff:   'New path exists and differs with original in type',
    PN.collides_diff: 'New path collides with another new path, and they differ in type',
    PN.exists_full:   'New path collides with a non-empty directory',
    PN.filter:        'Error from user-supplied filtering code: {} [original path: {}]',
    PN.rename:        'Error or invalid return from user-supplied renaming code: {} [original path: {}]',
})

FAILURE_NAMES = FN = constants('FailureNames', (
    'all_filtered',
    'parsing_no_paths',
    'parsing_paragraphs',
    'parsing_row',
    'parsing_imbalance',
    'user_code_exec',
))

FAILURE_FORMATS = constants('FailureFormats', {
    FN.all_filtered:           'All paths were filtered or skipped during processing',
    FN.parsing_no_paths:       'No input paths',
    FN.parsing_paragraphs:     'The --paragraphs option expects exactly two paragraphs',
    FN.parsing_row:            'The --rows option expects rows with exactly two cells: {!r}',
    FN.parsing_imbalance:      'Got an unequal number of original paths and new paths',
    FN.user_code_exec:         'Invalid user-supplied {} code:\n{}',
})

@dataclass(init = False, frozen = True)
class Issue:
    name: str
    msg: str

    FORMATS = None

    def __init__(self, name, *xs):
        # Custom initializer, because we need a convenience lookup to build
        # the ultimate message, given a problem/failure name and arguments.
        # To keep instances frozen, we modify __dict__ directly.
        d = self.__dict__
        d['name'] = name
        d['msg'] = self.FORMATS[name].format(*xs)

    @property
    def formatted(self):
        return with_newline(self.msg)

@dataclass(init = False, frozen = True)
class Problem(Issue):

    FORMATS = PROBLEM_FORMATS

@dataclass(init = False, frozen = True)
class Failure(Issue):

    FORMATS = FAILURE_FORMATS

####
# Problem controls.
####

CONTROLS = C = constants('Controls', (
    'halt',     # Halt RenamingPlan before any renaming occurs.
    'skip',     # Skip affected RenamePair (rp).
    'clobber',  # Delete rp.new before renaming old-to-new.
    'create',   # Create missing parent of rp.new before renaming old-to-new.
))

def pcname(control, problem):
    return underscores_to_hyphens(f'{control}-{problem}')

class ProblemControl:

    # A dict defining the valid controls for each Problem name.
    # The first control in each tuple is the default.
    # Values in comments could be allowed in the future.
    VALID_CONTROLS = {
        PN.equal:         (C.skip, C.halt),
        PN.same:          (C.skip, C.halt),
        PN.recase:        (C.skip, C.halt),
        PN.missing:       (C.skip, C.halt),
        PN.type:          (C.skip, C.halt),
        PN.parent:        (C.skip, C.halt, C.create),
        PN.exists:        (C.skip, C.halt, C.clobber),
        PN.collides:      (C.skip, C.halt, C.clobber),
        PN.exists_diff:   (C.skip, C.halt, C.clobber),
        PN.collides_diff: (C.skip, C.halt, C.clobber),
        PN.exists_full:   (C.skip, C.halt, C.clobber),
        PN.filter:        (C.halt, C.skip),
        PN.rename:        (C.halt, C.skip),
    }

    # A dict mapping each ProblemControl name to its
    # corresponding (PROBLEM_NAME, CONTROL_NAME) tuple.
    LOOKUP_BY_NAME = {
        pcname(c, prob) : (prob, c)
        for prob, controls in VALID_CONTROLS.items()
        for c in controls
    }

    # ProblemControl names: all of them.
    ALL_NAMES = tuple(LOOKUP_BY_NAME)

    # ProblemControl names: just the defaults.
    DEFAULTS = tuple(
        pcname(controls[0], prob)
        for prob, controls in VALID_CONTROLS.items()
    )

    # ProblemControl names: halt for all problems.
    HALT_ALL = tuple(
        pcname(C.halt, prob)
        for prob in VALID_CONTROLS
    )

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

