from dataclasses import dataclass, field
from short_con import constants, cons

from .utils import RenamePair

####
# Problem names and associated messages/formats.
#
# See command-line help text for more details on problems and their control.
####

PROBLEM_NAMES = PN = constants('ProblemNames', (
    # Controllable.
    'equal',
    'missing',
    'type',
    'parent',
    'existing',
    'colliding',
    'existing_diff',
    'colliding_diff',
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
    PN.equal:                  'Original path and new path are the same',
    PN.missing:                'Original path does not exist',
    PN.type:                   'Original path must be regular file or directory',
    PN.parent:                 'Parent directory of new path does not exist',
    PN.existing:               'New path exists',
    PN.colliding:              'New path collides with another new path',
    PN.existing_diff:          'New path exists and differs with original in type',
    PN.colliding_diff:         'New path collides with another new path, and they differ in type',
    # Not controllable.
    PN.all_filtered:           'All paths were filtered out by failure control during processing',
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
# Problem controls.
####

CONTROLS = constants('ProblemControls', (
    'skip',
    'clobber',
    'create',
))

CONTROLLABLES = {
    CONTROLS.skip: (
        PN.equal,
        PN.missing,
        PN.type,
        PN.parent,
        PN.existing,
        PN.colliding,
        PN.existing_diff,
        PN.colliding_diff,
    ),
    CONTROLS.clobber: (
        PN.existing,
        PN.colliding,
    ),
    CONTROLS.create: (
        PN.parent,
    ),
}

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

    @classmethod
    def format_for(cls, name):
        return PROBLEM_FORMATS[name]

    @classmethod
    def names_for(cls, control):
        return CONTROLLABLES[control]

