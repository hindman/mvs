
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

REASONS = constants('ProblemReasons',
    'invalid',
    'return_type',
)

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
))

@dataclass(frozen = True)
class PSpec:
    name: str
    controls: tuple[str]
    reasons: tuple[str]

    # REGISTRY = {}

    @classmethod
    def register(cls, name, *xs):
        controls = tuple(x for x in xs if x in CONTROLS)
        reasons = tuple([x for x in xs if x in REASONS] or [''])
        spec = cls(name, controls, reasons)
        # cls.REGISTRY.setdefault(name, spec)
        return spec

    # @classmethod
    # def lookup(cls, name):
    #     return cls.REGISTRY[name]

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

SPECS = (
    PSpec.new(PNAMES.equal, CONTROLS.skip),
    PSpec.new(PNAMES.missing, CONTROLS.skip),
    PSpec.new(PNAMES.missing_parent, CONTROLS.skip, CONTROLS.create),
    PSpec.new(PNAMES.existing_new, CONTROLS.skip, CONTROLS.clobber),
    PSpec.new(PNAMES.colliding_new, CONTROLS.skip, CONTROLS.clobber),
    PSpec.new(PNAMES.failed_rename, CONTROLS.skip, REASONS.invalid, REASONS.return_type),
    PSpec.new(PNAMES.failed_filter, CONTROLS.skip, CONTROLS.keep),
    PSpec.new(PNAMES.all_filtered),
    PSpec.new(PNAMES.control_conflict),
    PSpec.new(PNAMES.parsing_no_paths),
    PSpec.new(PNAMES.parsing_paragraphs),
    PSpec.new(PNAMES.parsing_row),
    PSpec.new(PNAMES.parsing_imbalance),
    PSpec.new(PNAMES.user_code_exec),
)

CONTROL_OPTS = tuple(
    f'{c}_{s.name}'
    for s in SPECS
    for c in s.controls
)

def control_opt(fname, control, for_opts):
    co = f'{control}_{fname}'
    if for_opts:
        return '--' + co.replace('_', '-')
    else:
        return co

'''

Solved:

    ** NOTE: This part can be done before converting the entire failure apparatus.

    Does a RenamePair need a Failure, or vice-versa?

        Neither. Plan below.

    Drop all Failure classes except for:

        @dataclass(frozen = True)
        class Failure:
            msg : str

        @dataclass(frozen = True)
        class RpFailure(Failure):
            rp : RenamePair

    Drop the failure attribute from RenamePair (and make it frozen too).

    Convert the rp-step-functions back to the simpler model of returning either
    the new-rp or a Failure.

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

    When a problem occurs, we need the ability to take the Failure and look up
    up which control (if any) has been requested by user.

        # Creating self.fconfig based on the user's settings.

        def create_failure_config(x, for_opts = False):
            fconfig = {}
            for co in CONTROL_OPTS:
                if getattr(x, co, False):
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

        # During prepare(), using a Failure to get the configured control.

        f = Failure(...)
        control = self.fconfig.get(f.name, None)

Solved:

    We need the ability to know when conflicting control-problem-kinds have been set
    True for the same problem-kind.

        Use create_failure_config() for both RenamingPlan and opts.

'''


