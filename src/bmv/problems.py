'''

Next:

    Search all usages of the following, fixing the pname values.

        PROBLEM_NAMES or PN
        FAILURE_NAMES or FM

        FAIL  =>  delete

    Try to run:

        bmv a b

Files:

    problems.py
    utils.py
    data_objects.py
    constants.py
    plan.py
    cli.py

'''

from dataclasses import dataclass, field
from short_con import constants, cons

from .data_objects import RenamePair

FAILURE_NAMES = constants('FailureNames', (
    'all_filtered',
    'parsing_no_paths',
    'parsing_paragraphs',
    'parsing_row',
    'parsing_imbalance',
    'user_code_exec',
))

PROBLEM_NAMES = constants('ProblemNames', (
    'equal',
    'missing',
    'existing',
    'colliding',
    'parent',
))

FN = FAILURE_NAMES
PN = PROBLEM_NAMES

FORMATS = constants('Formats', {
    # Failure.
    FN.all_filtered:       'All paths were filtered out by failure control during processing',
    FN.parsing_no_paths:   'No input paths',
    FN.parsing_paragraphs: 'The --paragraphs option expects exactly two paragraphs',
    FN.parsing_row:        'The --rows option expects rows with exactly two cells: {row!r}',
    FN.parsing_imbalance:  'Got an unequal number of original paths and new paths',
    FN.user_code_exec:     '{}',
    # Problem.
    PN.equal:              'Original path and new path are the same',
    PN.missing:            'Original path does not exist',
    PN.parent:             'Parent directory of new path does not exist',
    PN.existing:           'New path exists',
    PN.colliding:          'New path collides with another new path',
})

CONTROLS = constants('ProblemControls', (
    'skip',
    'clobber',
    'create',
))

CONTROLLABLES = {
    CONTROLS.skip:    PN.keys(),
    CONTROLS.clobber: (PN.existing, PN.colliding),
    CONTROLS.create:  (PN.parent,),
}

@dataclass(init = False, frozen = True)
class Failure:
    name: str
    msg: str

    def __init__(self, name, *xs):
        d = self.__dict__
        d['name'] = name
        d['msg'] = FORMATS[self.name].format(*xs)

    @property
    def formatted(self):
        return self.msg

@dataclass(init = False, frozen = True)
class Problem(Failure):

    @classmethod
    def names_for(cls, control):
        return CONTROLLABLES[control]

@dataclass(frozen = True)
class RpProblem(Problem):
    name : str
    msg : str
    rp : RenamePair

    @property
    def formatted(self):
        return f'{self.msg}:\n{self.rp.formatted}'

# TODO: drop this.
FAIL = cons('Fails',
    orig_missing = 'Original path does not exist',
    new_exists = 'New path exists',
    new_parent_missing = 'Parent directory of new path does not exist',
    orig_new_same = 'Original path and new path are the same',
    new_collision = 'New path collides with another new path',
    no_input_paths = 'No input paths',
    no_paths = 'No paths to be renamed',
    no_paths_after_processing = 'All paths were filtered out by failure control during processing',
    parsing_no_structures = 'No input structures given',
    parsing_row = 'The --rows option expects rows with exactly two cells: {row!r}',
    parsing_paragraphs = 'The --paragraphs option expects exactly two paragraphs',
    parsing_inequality = 'Got an unequal number of original paths and new paths',
    opts_require_one = 'One of these options is required',
    opts_mutex = 'No more than one of these options should be used',
    prepare_failed = 'RenamingPlan cannot rename paths because failures occurred during preparation',
    rename_done_already = 'RenamingPlan cannot rename paths because renaming has already been executed',
    conflicting_controls = 'Conflicting controls specified for a failure type: {} and {}',
    filter_code_invalid = 'Error in user-supplied filtering code: {} [original path: {}]',
    rename_code_invalid = 'Error in user-supplied renaming code: {} [original path: {}]',
    rename_code_bad_return = 'Invalid type from user-supplied renaming code: {} [original path: {}]',
    prepare_failed_cli = 'Renaming preparation resulted in failures:{}.\n',
    renaming_raised = '\nRenaming raised an error; some paths might have been renamed; traceback follows:\n\n{}',
)

