from dataclasses import dataclass
from short_con import constants

from .constants import CON
from .messages import MSG_FORMATS as MF

from .utils import(
    MvsError,
    underscores_to_hyphens,
    hyphen_join,
    with_newline,
    validated_choices,
)

####
#
# Failures and Problems: general notes.
#
# Failures are not specific to a single Renaming and/or have
# no meaningful resolution. Most relate to bad inputs.
#
# Problems are specific to one Renaming. Some of them are resolvable, some not.
# Renamings with unresolvable problems must be skipped/excluded; those with
# resolvable problems can be skipped if the user requests it. Both classes
# have a name, and an optional variety to further classify them.
#
#   Resolvable | Name      | Varieties
#   ----------------------------------------------
#   no         | noop      | equal, same, recase
#   no         | duplicate | .
#   no         | missing   | .
#   no         | type      | .
#   no         | code      | filter, rename
#   no         | exists    | other
#   ----------------------------------------------
#   yes        | exists    | diff, full
#   yes        | collides  | diff, full
#   yes        | parent    | .
#
# See command-line help text for more details.
#
####

####
# Names, varieties, and formats.
####

FAILURE_NAMES = FN = constants('FailureNames', (
    'all_filtered',
    'parsing',
    'code',
    'strict',
))

FAILURE_VARIETIES = FV = constants('FailureVarieties', (
    'no_paths',
    'paragraphs',
    'row',
    'imbalance',
))

FAILURE_FORMATS = FF = {
    (FN.all_filtered, None):     'all paths were filtered, excluded, or skipped during processing.',
    (FN.parsing, FV.no_paths):   'no input paths.',
    (FN.parsing, FV.paragraphs): 'the --paragraphs option expects exactly two paragraphs.',
    (FN.parsing, FV.row):        'the --rows option expects rows with exactly two cells: {!r}.',
    (FN.parsing, FV.imbalance):  'got an unequal number of original paths and new paths.',
    (FN.code, None):             'invalid user-supplied {} code:\n{}',
    (FN.strict, None):           'renaming plan failed to satisfy strict: {!r}.',
}

PROBLEM_NAMES = PN = constants('ProblemNames', (
    'noop',
    'duplicate',
    'missing',
    'type',
    'code',
    'exists',
    'collides',
    'parent',
))

PROBLEM_VARIETIES = PV = constants('ProblemVarieties', (
    'equal',
    'same',
    'recase',
    'filter',
    'rename',
    'other',
    'diff',
    'full',
))

PROBLEM_FORMATS = PF = {
    # Unresolvable.
    (PN.noop, PV.equal):    'Original path and new path are the exactly equal',
    (PN.noop, PV.same):     'Original path and new path are the functionally the same',
    (PN.noop, PV.recase):   'User requested path-name case-change, but file system already agrees with new',
    (PN.missing, None):     'Original path does not exist',
    (PN.duplicate, None):   'Original path is the same as another original path',
    (PN.type, None):        'Original path is neither a regular file nor directory',
    (PN.code, PV.filter):   'Error from user-supplied filtering code: {} [original path: {}]',
    (PN.code, PV.rename):   'Error or invalid return from user-supplied renaming code: {} [original path: {}]',
    (PN.exists, PV.other):  'New path exists and is neither regular file nor directory',
    # Resolvable.
    (PN.exists, None):      'New path exists',
    (PN.exists, PV.diff):   'New path exists and differs with original in type',
    (PN.exists, PV.full):   'New path exists and is a non-empty directory',
    (PN.collides, None):    'New path collides with another new path',
    (PN.collides, PV.diff): 'New path collides with another new path, and they differ in type',
    (PN.collides, PV.full): 'New path collides with another new path, and it is a non-empty directory',
    (PN.parent, None):      'Parent directory of new path does not exist',
}

####
# Issue: a base class.
####

@dataclass(init = False, frozen = True)
class Issue:
    name: str
    variety: str
    msg: str

    FORMATS = None

    def __init__(self, name, *xs, variety = None):
        # Custom initializer, because we need to build the ultimate msg from
        # the name, variety, and arguments. To keep instances frozen,
        # we update __dict__ directly.
        try:
            msg = self.FORMATS[name, variety].format(*xs)
        except KeyError:
            raise MvsError(MF.invalid_problem.format(name, variety))
        self.__dict__.update(
            name = name,
            variety = variety,
            msg = msg,
        )

####
# Failure.
####

@dataclass(init = False, frozen = True)
class Failure(Issue):

    FORMATS = FAILURE_FORMATS

####
# Problem.
####

@dataclass(init = False, frozen = True)
class Problem(Issue):

    FORMATS = PROBLEM_FORMATS

    RESOLVABLE = (
        (PN.exists, None),
        (PN.exists, PV.diff),
        (PN.exists, PV.full),
        (PN.collides, None),
        (PN.collides, PV.diff),
        (PN.collides, PV.full),
        (PN.parent, None),
    )

    STR_IDS = tuple(hyphen_join(*tup) for tup in RESOLVABLE)
    SKIP_CHOICES = (CON.all, *STR_IDS)

    @classmethod
    def is_resolvable(cls, prob):
        return (prob.name, prob.variety) in cls.RESOLVABLE

    @property
    def sid(self):
        # Problems have a str ID, which is just the NAME-VARIETY string that a
        # user provides when declaring which kinds of resolvable problems
        # should cause a Renaming to be skipped. These IDs are also used in the
        # CliRenamer's summary tally.
        return hyphen_join(self.name, self.variety)

    @classmethod
    def from_str_id(cls, sid):
        # Takes a Problem str ID.
        # Returns the corresponding Problem or raises.
        xs = underscores_to_hyphens(sid).split(CON.hyphen)
        if len(xs) > 2:
            raise MvsError(MF.invalid_skip.format(sid))
        name, variety = (xs + [None])[0:2]
        return cls(name, variety = variety)

    @classmethod
    def probs_matching_sid(cls, sid):
        # Takes a str ID.
        # Returns all resolvable problems matching that ID.
        query = cls.from_str_id(sid)
        return tuple(
            cls(name, variety = variety)
            for name, variety in cls.RESOLVABLE
            if name == query.name and query.variety in (variety, None)
        )

####
# Strict mode.
#
# A data object to encapsulate the user's strict settings.
####

@dataclass(frozen = True)
class StrictMode:
    excluded: bool
    probs: tuple

    EXCLUDED = 'excluded'
    STRICT_PROBS = (PN.parent, PN.exists, PN.collides)
    CHOICES = (CON.all, EXCLUDED, *STRICT_PROBS)

    @classmethod
    def from_user(cls, strict):
        # Normalize and validate.
        try:
            xs = validated_choices(strict, StrictMode.CHOICES)
        except Exception:
            raise MvsError(MF.invalid_strict.format(strict))
        # Return a StrictMode.
        EX = cls.EXCLUDED
        probs = tuple(x for x in xs if x != EX)
        return cls(EX in xs, probs)

    @property
    def as_str(self):
        xs = (
            self.EXCLUDED if self.excluded else None,
            *self.probs,
        )
        return CON.space.join(filter(None, xs))

