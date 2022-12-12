from dataclasses import dataclass
from short_con import constants, cons

'''

Next steps:

    Define FAILURE_FORMATS.

    Then what? Any way to make the transition in incremental steps??

Naming and modeling:

    A Failure has a name that declares its kind/type. In some cases, it has a
    reason, which does not alter its kind but does determine which
    format-string it uses to build the the msg of the Failure.

    The user-facing failure-control mechanisms also use the Failure names (eg,
    missing_parent), prefixed by the desired control (eg, skip_missing_parent
    for a RenamingPlan or --skip_missing_parent in a command-line context).

Drop all Failure classes except for:

    @dataclass(frozen = True)
    class Failure:
        msg : str

    @dataclass(frozen = True)
    class RpFailure(Failure):
        rp : RenamePair

Creating the right kind of Failure with the appropriate

    # Usage in code:
    # - Simple
    # - With format-args.
    # - With format-args and reason.

    from .problems import FAILURE_NAMES as FN

    f1 = Failure(FN.equal)
    f2 = Failure(FN.conflicting_controls, name1, name2)
    f3 = Failure(FN.rename_fail_invalid, e, rp.orig, reason = REASONS.return_type)

Given a Failure, look up the failure-control, if any:

    f = Failure(...)
    control = self.fconfig.get(f.name, None)

'''


FAILURE_NAMES = constants('FailureNames', (
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

CONTROLS = constants('FailureControls', (
    'skip',
    'keep',
    'create',
    'clobber',
))

REASONS = constants('FailureReasons', (
    'invalid',
    'return_type',
))

FAILURE_FORMATS = cons('FailureFormats',
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

class Failure:

    FN = FAILURE_NAMES
    C = CONTROLS
    R = REASONS

    DEFINITIONS = {
        # Failure name          Valid controls        Valid reasons
        FN.equal              : [[C.skip],            []],
        FN.missing            : [[C.skip],            []],
        FN.missing_parent     : [[C.skip, C.create],  []],
        FN.existing_new       : [[C.skip, C.clobber], []],
        FN.colliding_new      : [[C.skip, C.clobber], []],
        FN.failed_rename      : [[C.skip],            [R.invalid, R.return_type]],
        FN.failed_filter      : [[C.skip, C.keep],    []],
        FN.all_filtered       : [[],                  []],
        FN.control_conflict   : [[],                  []],
        FN.parsing_no_paths   : [[],                  []],
        FN.parsing_paragraphs : [[],                  []],
        FN.parsing_row        : [[],                  []],
        FN.parsing_imbalance  : [[],                  []],
        FN.user_code_exec     : [[],                  []],
    }

    def __init__(self, name, *xs, reason = ''):
        self.name = name
        self.reason = reason
        self.msg = FAILURE_FORMATS[self.fmt_name].format(*xs)

    @property
    def fmt_name(self):
        if self.reason:
            return f'{self.name}_{self.reason}'
        else:
            return self.name

    @classmethod
    def create_failure_config(cls, x, for_opts = False):
        fconfig = {}
        for co_name in cls.control_opt_names():
            if getattr(x, co_name, None):
                control, fname = co_name.split('_', 1)
                if fname in fconfig:
                    cos = tuple(
                        cls.control_opt_for_user(fname, c, for_opts)
                        for c in (control, fconfig[fname])
                    )
                    return cls(FAILURE_NAMES.control_conflict, *cos)
                else:
                    fconfig[fname] = control
        return fconfig

    @classmethod
    def control_opt_names(cls):
        return tuple(
            f'{c}_{p.name}'
            for fname, (controls, reasons) in cls.DEFINITIONS.items()
            for c in controls
        )

    @staticmethod
    def control_opt_for_user(fname, control, for_opts):
        co = f'{control}_{fname}'
        if for_opts:
            return '--' + co.replace('_', '-')
        else:
            return co

