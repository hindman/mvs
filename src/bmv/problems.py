'''

Next:

    Working through remaining problems:

        - Resurrect the conflicting_controls msg from Git.

        test_some_failed_rps
        test_filter_all
        test_no_input_paths
        test_log

    Full code read with an eye toward problem-related code and messages.

'''

from dataclasses import dataclass, field
from short_con import constants, cons

from .data_objects import RenamePair

PROBLEM_NAMES = constants('ProblemNames', (
    # Controllable.
    'equal',
    'missing',
    'existing',
    'colliding',
    'parent',
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
    # BmvError.
    'rename_done_already',
    'prepare_failed',
    # Command-line messages.
    'prepare_failed_cli',
    'renaming_raised',
    'opts_require_one',
    'opts_mutex',
))

PN = PROBLEM_NAMES

PROBLEM_FORMATS = constants('ProblemFormats', {
    # Controllable.
    PN.equal:                  'Original path and new path are the same',
    PN.missing:                'Original path does not exist',
    PN.parent:                 'Parent directory of new path does not exist',
    PN.existing:               'New path exists',
    PN.colliding:              'New path collides with another new path',
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
    # BmvError.
    PN.rename_done_already:    'RenamingPlan cannot rename paths because renaming has already been executed',
    PN.prepare_failed:         'RenamingPlan cannot rename paths because failures occurred during preparation',
    # Command-line messages.
    PN.prepare_failed_cli:     'Renaming preparation resulted in failures:{}.\n',
    PN.renaming_raised:        '\nRenaming raised an error; some paths might have been renamed; traceback follows:\n\n{}',
    PN.opts_require_one:       'One of these options is required',
    PN.opts_mutex:             'No more than one of these options should be used',
})

CONTROLS = constants('ProblemControls', (
    'skip',
    'clobber',
    'create',
))

CONTROLLABLES = {
    CONTROLS.skip:    (PN.equal, PN.missing, PN.parent, PN.existing, PN.colliding),
    CONTROLS.clobber: (PN.existing, PN.colliding),
    CONTROLS.create:  (PN.parent,),
}

@dataclass(init = False, frozen = True)
class Problem:
    name: str
    msg: str
    rp : RenamePair = None

    def __init__(self, name, *xs, msg = None, rp = None):
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

