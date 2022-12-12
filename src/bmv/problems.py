from dataclasses import dataclass
from short_con import constants, cons

'''

============================================================
Overview
============================================================

First, drop the rename and filter problems:

    - If the user's code is bad, they can and should fix it.

    - That also removes the keep control.

    - And eliminates the need for Problem.reason.

The argparse help text would look like the following (ugly, as always, but
better than the current situation).

    Problem-control options:

        --skip {all|equal|missing|parent|existing|colliding}...
                                         Skip paths with problems, but proceed with others.
        --clobber {all|existing|colliding}
                                         Rename anyway, in spite of overwriting.
        --create {parent}                Create missing parent before renaming.

In the epilogue, we could explain how problem control works:

    Before any renaming occurs, each pair of original and new paths is checked
    for common types of problems. By default, if any occur, the renaming plan
    is halted and no paths are renamed. The problems and their short names are
    as follows:

        equal     | Original path and new path are the same.
        missing   | Original path does not exist.
        existing  | New path already exists.
        colliding | Two or more new paths are the same.
        parent    | Parent directory of new path does not exist.

    Users can configure various problem controls to address such issues. That
    allows the renaming plan to proceed in spite of the problems, either by
    skipping offending items, taking remedial action, or simply forging ahead
    in spite of the consequences. As shown in the usage documentation above,
    the --create control applies only to a single type of problem, the
    --clobber control can apply to multiple, and the --skip control can apply
    to any or all. Here are some examples to illustrate usage:

        --skip equal         | Skip items with 'equal' problem.
        --skip equal missing | Skip items with 'equal' or 'missing' problems.
        --skip all           | Skip items with any type of problem.
        --clobber all        | Rename in spite of 'existing' and 'colliding' problems.
        --create parent      | Create missing parent before renaming.
        --create             | Same thing, more compactly.

If we were to take that approach:

    - User interface: better.

    - Validation of options/kwargs: much simpler.

    - Ability to create the right kind of Problem: the same.

    - Ability to look up a control when a Problem occurs: the same [this
      operation is downstream of the validation logic, which can create the
      needed lookup data-structure].

============================================================
Details
============================================================

Define PROBLEM_FORMATS.

Importing relationships:

    __init__.py
        from .version import __version__

    cli.py
        from .data_objects import Failure
        from .plan import RenamingPlan, validated_failure_controls
        from .version import __version__
        from .constants import ...
        from .utils import ...

    plan.py
        from .constants import ...
        from .utils import validated_failure_controls
        from .data_objects import ...

    utils.py
        from .data_objects import OptsFailure
        from .constants import ...

    constants.py
        from .data_objects import ...

    data_objects.py
        .

    problems.py
        .

Drop all Problem classes except for:

    @dataclass(frozen = True)
    class Problem:
        msg : str

    @dataclass(frozen = True)
    class RpProblem(Problem):
        rp : RenamePair

How to configure argparse:

    {
        group: 'Problem control',
        names: '--skip',
        'choices': CON.all_tup + Problem.names_for(CONTROLS.skip),
        'help': 'Skip items with problems, but proceed with others',
    },

Validate and normalize control settings during RenamingPlan.__init__():

    self.skip = self.validated_pnames(CONTROLS.skip, skip)
    self.clobber = ...
    self.create = ...

    def validated_pnames(self, control, pnames):
        if not pnames:
            return ()

        all_choices = Problem.names_for(control)
        invalid = tuple(nm for nm in pnames if nm not in all_choices)

        if invalid:
            raise
        elif CON.all in pnames:
            return all_choices
        else:
            return pnames

Create the lookup from Problem to control, during RenamingPlan.__init__():

    self.control_lookup = self.build_control_lookup()

    def build_control_lookup(self):
        return {
            pname : control
            for control in CONTROLS.keys():
            for pname in getattr(self, control):
        }

Creating the right kind of Problem with the appropriate msg:

    from .problems import PROBLEM_NAMES as PN

    p1 = Problem(PN.equal)
    p2 = Problem(PN.parsing_row, row)

Given a Problem, look up the problem-control, if any:

    p = Problem(...)
    control = self.control_lookup.get(p.name, None)

'''

PROBLEM_NAMES = constants('ProblemNames', (
    'equal',
    'missing',
    'existing_new',
    'colliding_new',
    'missing_parent',
    'all_filtered',
    'parsing_no_paths',
    'parsing_paragraphs',
    'parsing_row',
    'parsing_imbalance',
    'user_code_exec',
))

PN = PROBLEM_NAMES

PROBLEM_FORMATS = constants('ProblemFormats', {
    PN.equal:              '...',
    PN.missing:            '...',
    PN.missing_parent:     '...',
    PN.existing_new:       '...',
    PN.colliding_new:      '...',
    PN.all_filtered:       '...',
    PN.parsing_no_paths:   '...',
    PN.parsing_paragraphs: '...',
    PN.parsing_row:        '...',
    PN.parsing_imbalance:  '...',
    PN.user_code_exec:     '...',
})

CONTROLS = constants('ProblemControls', (
    'skip',
    'clobber',
    'create',
))

VALID_CONTROLS = {
    PN.equal              : [CONTROLS.skip],
    PN.missing            : [CONTROLS.skip],
    PN.missing_parent     : [CONTROLS.skip, CONTROLS.create],
    PN.existing_new       : [CONTROLS.skip, CONTROLS.clobber],
    PN.colliding_new      : [CONTROLS.skip, CONTROLS.clobber],
    PN.all_filtered       : [],
    PN.parsing_no_paths   : [],
    PN.parsing_paragraphs : [],
    PN.parsing_row        : [],
    PN.parsing_imbalance  : [],
    PN.user_code_exec     : [],
}

class Problem:

    def __init__(self, name, *xs):
        self.name = name
        self.msg = PROBLEM_FORMATS[self.name].format(*xs)

    def __str__(self):
        return repr(self)

    def __repr__(self):
        return f'Problem({self.name}, {self.msg!r})'

    @classmethod
    def names_for(cls, control):
        return tuple(
            fname
            for fname, controls in cls.VALID_CONTROLS.items()
            if control in controls
        )

