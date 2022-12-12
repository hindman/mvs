from dataclasses import dataclass
from short_con import constants, cons

'''

----------------------------
Let's take another step back
----------------------------

The following approach could simplify validation and reduce the bulk of the
user-interace (proliferation of failure-control options/kwargs).

The argparse help text would look like this:

    Failure control options:

        --skip {all|equal|missing|parent|existing|colliding|rename|filter}...
                                         Skip paths with failures, but proceed with others.
        --clobber [all|existing|colliding]
                                         Rename anyway, in spite of overwriting.
        --create [parent]                Create missing parent before renaming.
        --keep [filter]                  Retain the item anyway.

In the epilogue, we could explain how failure control works:

    Before any renaming occurs, each pair of original and new paths is checked
    for common types of problems. By default, if any occur, the renaming plan
    is halted and no paths are renamed. The failures and their short names are
    as follows:

        equal     | Original path and new path are the same.
        missing   | Original path does not exist.
        existing  | New path already exists.
        colliding | Two or more new paths are the same.
        parent    | Parent directory of new path does not exist.
        rename    | User's renaming code fails during execution.
        filter    | User's filtering code fails during execution.

    Users can configure various failure controls to address such issues. That
    allows the renaming plan to proceed in spite of the problems, either by
    skipping offending items, taking remedial action, or simply forging ahead
    in spite of the consequences. As shown is the usage documentation above,
    some controls are applicable only to a single type of problem, others apply
    to multiple, and the skip control can be applied to any or all of them.
    Here are some examples to illustrate usage:

        --skip equal         | Skip items with 'equal' failure.
        --skip equal missing | Skip items with 'equal' or 'missing' failures.
        --skip all           | Skip items with any type of failure.
        --create parent      | Create missing parent before renaming.
        --create             | Same thing, more compactly.

If we were to take that approach:

    - User interface: better.

    - Validation of options/kwargs: much simpler.

    - Ability to create the right kind of Failure: the same.

    - Ability to look up a control when a Failure occurs: the same [this
      operation is downstream of the validation logic, which can create the
      needed lookup data-structure].

============================================================


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
        FN.parsing_no_paths   : [[],                  []],   # Use REASONS instead of 4 parsing definitions?
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

