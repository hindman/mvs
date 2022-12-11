from dataclasses import dataclass
from short_con import constants, cons

PNAMES = constants('ProblemNames', (
    'equal',
    'missing',
    'missing_parent',
    'existing_new',
    'colliding_new',
    'failed_rename',
    'failed_filter',
    'all_filtered',
    'control_conflict',
    'parsing_no_paths',
    'parsing_paragraphs',
    'parsing_row',
    'parsing_imbalance',
    'user_code_exec',
))

CONTROLS = constants('ProblemControls', (
    'skip',
    'keep',
    'create',
    'clobber',
))

REASONS = constants('ProblemReasons', (
    'invalid',
    'return_type',
))

PFORMATS = cons('ProblemFormats',
    equal                 = '...',
    missing               = '...',
    missing_parent        = '...',
    existing_new          = '...',
    colliding_new         = '...',
    failed_rename_invalid = '...',
    failed_rename_return  = '...',
    failed_filter         = '...',
    all_filtered          = '...',
    control_conflict      = '...',
    parsing_no_paths      = '...',
    parsing_paragraphs    = '...',
    parsing_row           = '...',
    parsing_imbalance     = '...',
    user_code_exec        = '...',
)

@dataclass(frozen = True)
class Problem:
    name: str
    controls: tuple[str]
    reasons: tuple[str]

    DEFINITIONS = (
        (PNAMES.equal, CONTROLS.skip),
        (PNAMES.missing, CONTROLS.skip),
        (PNAMES.missing_parent, CONTROLS.skip, CONTROLS.create),
        (PNAMES.existing_new, CONTROLS.skip, CONTROLS.clobber),
        (PNAMES.colliding_new, CONTROLS.skip, CONTROLS.clobber),
        (PNAMES.failed_rename, CONTROLS.skip, REASONS.invalid, REASONS.return_type),
        (PNAMES.failed_filter, CONTROLS.skip, CONTROLS.keep),
        (PNAMES.all_filtered),
        (PNAMES.control_conflict),
        (PNAMES.parsing_no_paths),
        (PNAMES.parsing_paragraphs),
        (PNAMES.parsing_row),
        (PNAMES.parsing_imbalance),
        (PNAMES.user_code_exec),
    )

    @classmethod
    def new(cls, name, *xs):
        controls = tuple(x for x in xs if x in CONTROLS)
        reasons = tuple([x for x in xs if x in REASONS] or [''])
        return cls(name, controls, reasons)

    @classmethod
    def generate_all(cls):
        return tuple(cls.new(*tup) for tup in cls.DEFINITIONS)

PROBLEMS = Problem.generate_all()

class Failure:

    def __init__(self, name, *xs, reason = ''):
        self.name = name
        self.reason = reason
        self.msg = PFORMATS[self.fmt_name].format(*xs)

    @property
    def fmt_name(self):
        if self.reason:
            return f'{self.name}_{self.reason}'
        else:
            return self.name

CONTROL_OPTS = tuple(
    f'{c}_{p.name}'
    for p in PROBLEMS
    for c in p.controls
)

def create_failure_config(x, for_opts = False):
    fconfig = {}
    for co in CONTROL_OPTS:
        if getattr(x, co, None):
            control, fname = co.split('_', 1)
            if fname in fconfig:
                cos = tuple(
                    control_opt(fname, c, for_opts)
                    for c in (control, fconfig[fname])
                )
                return Failure(PNAMES.control_conflict, *cos)
            else:
                fconfig[fname] = control
    return fconfig

def control_opt(fname, control, for_opts):
    co = f'{control}_{fname}'
    if for_opts:
        return '--' + co.replace('_', '-')
    else:
        return co

'''

Naming and modeling:

    A Problem in a generic representation of something that can go wrong. A
    Failure is the specific occurrence of a Problem -- most importantly the msg
    attribute describing what went wrong, sometimes with specific data values
    for the case at hand plugged into the msg.

    A specific Failure and its corresponding generic Problem are linked via
    their name attribute, which declares their kind/type. Failure instances
    have an additional attribute (reason) that can further classify the Failure
    when building the specific failure msg.

    The user-facing failure-control mechanisms also use the Failure/Problem
    names (eg, missing_parent), prefixed by the desired control (eg,
    skip_missing_parent=True for a RenamingPlan, or --skip_missing_parent in a
    command-line usage).

Solved:

    Does a RenamePair need a Failure, or vice-versa?

        Neither.

    PHASE I

        ** NOTE: This part can be done before converting the entire failure apparatus.

        Drop the failure attribute from RenamePair (and make it frozen too).

        Convert the rp-step-functions back to the simpler model of returning
        either the new-rp or a Failure.

        Then adjust the processing generator accordingly:

            def processed_rps(self, step):
                ...
                result = step(rp, next(seq))
                if isinstance(result, Failure):
                    control = self.handle_failure(result, rp)
                else:
                    control = None
                    rp = result
                ...

    PHASE II

        Drop all Failure classes except for:

            @dataclass(frozen = True)
            class Failure:
                msg : str

            @dataclass(frozen = True)
            class RpFailure(Failure):
                rp : RenamePair

Solved:

    We need the ability to generate all of the control-problem-kinds (as flags).

        See CONTROL_OPTS.

Solved:

    When a problem occurs, we need the ability to create the right kind of
    Failure with the appropriate message.

    # Usage in code:
    # - Simple
    # - With format-args.
    # - With format-args and reason.

    f1 = Failure(PNAMES.equal)
    f2 = Failure(PNAMES.conflicting_controls, name1, name2)
    f3 = Failure(PNAMES.rename_fail_invalid, e, rp.orig, reason = REASONS.return_type)

Solved:

    We need the ability to know when conflicting control-problem-kinds have been set
    True for the same problem-kind.

        Use create_failure_config(), which validates and creates, for both
        RenamingPlan and opts.

Solved:

    When a problem occurs, we need the ability to take the Failure and look up
    up which control (if any) has been requested by user.

        f = Failure(...)
        control = self.fconfig.get(f.name, None)

'''


