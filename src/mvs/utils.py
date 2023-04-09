import os
import pyperclip
import stat
import sys

from dataclasses import dataclass
from inspect import getsource
from kwexception import Kwexception
from pathlib import Path
from short_con import constants
from subprocess import run
from tempfile import gettempdir, TemporaryDirectory
from textwrap import dedent
from time import time

from .version import __version__

####
# General constants.
####

class CON:
    # Application configuration.
    app_name = 'mvs'
    encoding = 'utf-8'
    app_dir_env_var = f'{app_name.upper()}_APP_DIR'

    # Characters and simple tokens.
    newline = '\n'
    para_break = newline + newline
    space = ' '
    tab = '\t'
    colon = ':'
    pipe = '|'
    period = '.'
    comma_join = ', '
    underscore = '_'
    hyphen = '-'
    comma_space = ', '
    dash = hyphen + hyphen
    all = 'all'
    all_tup = (all,)
    yes = 'yes'

    # User-supplied code.
    code_actions = constants('CodeActions', ('rename', 'filter'))
    user_code_fmt = 'def {func_name}(o, p, seq, plan):\n{indent}{user_code}\n'
    func_name_fmt = '_do_{}'

    # Command-line exit codes.
    exit_ok = 0
    exit_fail = 1

    # Logging.
    datetime_fmt = '%Y-%m-%d_%H-%M-%S'
    logfile_ext = 'json'
    prefs_file_name = 'config.json'

    # Executables.
    default_pager_cmd = 'more'
    default_editor_cmd = 'vim'

####
# Structures for input paths data.
####

STRUCTURES = constants('Structures', (
    'paragraphs',
    'flat',
    'pairs',
    'rows',
))

####
# Message formats.
####

SUMMARY_TABLE = '''
Summary:
    Inputs: {n_initial}
    ----
    Renamings: {n_active}
    Filtered: {n_filtered}
    Skipped: {n_skipped}
    ----
    Create parent: {n_create}
    Clobber existing: {n_clobber}
'''


MSG_FORMATS = MF = constants('MsgFormats', dict(
    # MvsError instances in RenamingPlan.
    rename_done_already    = 'RenamingPlan cannot rename paths because renaming has already been executed',
    prepare_failed         = 'RenamingPlan cannot rename paths because failures occurred during preparation',
    invalid_control        = 'Invalid problem control: {!r}',
    invalid_skip           = 'Invalid value for RenamingPlan.skip: {!r}',
    invalid_strict         = 'Invalid value for RenamingPlan.strict: {!r}',
    conflicting_controls   = 'Conflicting controls for problem {!r}: {!r} and {!r}',
    invalid_controls       = 'Invalid value for RenamingPlan controls parameter',
    unrequested_clobber    = 'Renaming would cause unrequested clobbering to occur',
    unsupported_clobber    = 'Renaming would cause unsupported path type to be clobbered',
    # Error messages in CliRenamer.
    path_collection_failed = 'Collection of input paths failed.\n\n{}',
    plan_creation_failed   = 'Unexpected error during creation of renaming plan.\n\n{}',
    log_writing_failed     = 'Unexpected error during writing to log file.\n\n{}',
    prefs_reading_failed   = 'Unexpected error during reading of user preferences {!r}.\n\n{{}}',
    renaming_raised        = '\nRenaming raised an error at tracking_index={}. Traceback follows:\n\n{{}}',
    opts_require_one       = 'One of these options is required',
    opts_mutex             = 'No more than one of these options should be used',
    invalid_pref_val       = 'User preferences: invalid value for {}: expected {}: got {!r}',
    invalid_pref_keys      = 'User preferences: invalid key(s): {}',
    no_editor              = 'The --edit option requires an --editor',
    editor_cmd_nonzero     = 'Editor process exited unsuccessfully: editor={!r}, path={!r}',
    edit_failed_unexpected = 'Editing failed unexpectedly. Traceback follows:\n\n{}',
    # Other messages in CliRenamer.
    summary_table          = SUMMARY_TABLE.lstrip(),
    listing_rename         = 'Paths to be renamed{}:\n',
    listing_filter         = 'Renamings filtered out by user code{}:\n',
    listing_skip           = 'Renamings skipped due to problems{}:\n',
    listing_create         = 'Renamings that will create new parent{}:\n',
    listing_clobber        = 'Renamings that will clobber existing paths{}:\n',
    listing_failures       = 'General failures during preparation{}:\n',
    listing_halts          = 'Renamings that halted the renaming plan during preparation{}:\n',
    confirm_prompt         = '\nRename paths',
    no_action_msg          = '\nNo action taken.',
    paths_renamed_msg      = '\nPaths renamed.',
    cli_version_msg        = f'{CON.app_name} v{__version__}',
))

####
# Types of renaming changes affecting the name-portion of a path.
####

NAME_CHANGE_TYPES = constants('NameChangeTypes', (
    'noop',
    'name_change',
    'case_change',
))

####
# An exception class for the project.
####

class MvsError(Kwexception):
    pass

####
# Read/write: files, clipboard.
####

def read_from_file(path):
    with open(path) as fh:
        return fh.read()

def edit_text(editor, text):
    # Get a temp file path that does not exist.
    while True:
        now = str(time()).replace(CON.period, '')
        path = Path(gettempdir()) / f'{CON.app_name}.{now}.txt'
        if not path.is_file():
            path = str(path)
            break

    # Write current text to it.
    with open(path, 'w') as fh:
        fh.write(text)

    # Let user edit the file.
    q = '"' if sys.platform == 'win32' else "'"
    cmd = f"{editor} {q}{path}{q}"
    p = run(cmd, shell = True)

    # Read file and return its edited text.
    if p.returncode == 0:
        with open(path) as fh:
            return fh.read()
    else:
        raise MvsError(MSG_FORMATS.editor_cmd_nonzero.format(editor, path))

def read_from_clipboard():
    return pyperclip.paste()

def write_to_clipboard(text):
    pyperclip.copy(text)

####
# Functions given to argparse to convert or validate arguments.
####

def positive_int(x):
    if x.isdigit():
        x = int(x)
        if x >= 1:
            return x
    raise ValueError

def seq_or_str(xs):
    # Takes a sequence or space-delimited string.
    # Returns a tuple.
    if xs is None:
        return ()
    elif isinstance(xs, str):
        return tuple(xs.split())
    else:
        return tuple(xs)

####
# A class to hold configuration information for each argparse add_argument()
# call, along with other information used by the mvs library validate
# user-preferences and to merge user-preferences with command-line arguments.
####

class OptConfig:

    def __init__(self,
                 group = None,
                 names = None,
                 validator = None,
                 real_default = None,
                 **params):
        # Whether start a new argparse group before calling add_argument().
        self.group = group

        # The names supplied to add_argument(): eg, ('--help', '-h').
        # And the corresponding opt name: eg, 'help'.
        self.names = names.split()
        self.name = self.names[0].lstrip(CON.hyphen)

        # All other keyword parameters passed to add_argument().
        self.params = params

        # Whether the opt is a flag. We use this to set the argparse
        # choices setting for the --disable option.
        self.is_flag = params.get('action', None) == 'store_true'

        # An object used to validate user-preferences. See check_value().
        self.validator = validator

        # When configuring argparse, we always supply "empty" defaults (False,
        # None, or []). After we get opts from argparse, if an opt still has an
        # empty value, we know the user did not supply anything on the command
        # line -- which means we can safely apply either the real_default or a
        # value from user preferences.
        self.real_default = real_default

    def check_value(self, val):
        # If the validator is already a type (bool, int, etc), just
        # check the value's type and return None or the expected type name.
        # Otherwise, the validator is one of the staticmethod validator
        # functions defined in OptConfig. Those function behave in a
        # similar fashion: None for OK, str with expected type for invalid.
        f = self.validator
        if isinstance(f, type):
            if isinstance(val, f):
                return None
            else:
                return f.__name__
        else:
            return f(val)

    @staticmethod
    def posint(x):
        ok = (
            isinstance(x, int) and
            x >= 1 and
            not isinstance(x, bool)
        )
        if ok:
            return None
        else:
            return 'positive int'

    @staticmethod
    def list_of_str(xs):
        if isinstance(xs, list) and all(isinstance(x, str) for x in xs):
            return None
        else:
            return 'list[str]'

####
# Text wrapping and other string conversion utilities.
####

def underscores_to_hyphens(s):
    return s.replace(CON.underscore, CON.hyphen)

def hyphens_to_underscores(s):
    return s.replace(CON.hyphen, CON.underscore)

def with_newline(s):
    if s.endswith(CON.newline):
        return s
    else:
        return s + CON.newline

def wrap_text(text, width):
    # Takes some text and a max width.
    # Wraps the text to the desired width and returns it.

    # Convenience vars.
    NL = CON.newline
    SP = CON.space

    # Split text into words. If none, return immediately.
    words = [
        w
        for line in text.split(NL)
        for w in line.strip().split(SP)
    ]
    if not words: # pragma: no cover
        return ''

    # Assemble the words into a list-of-list, where each
    # inner list will become a line within the width limit.
    lines = [[]]
    tot = 0
    for w in words:
        n = len(w)
        if n == 0: # pragma: no cover
            continue
        elif tot + n + 1 <= width:
            lines[-1].append(w)
            tot += n + 1
        else:
            lines.append([w])
            tot = n

    # Join the words back into a paragraph of text.
    return NL.join(
        SP.join(line)
        for line in lines
    )

def get_source_code(x):
    # Helper used to get source code for the
    # user-supplied renaming/filtering code.
    if callable(x):
        return getsource(x)
    else:
        return str(x)

####
# Constants and functions for path type and existence-status.
####

PATH_TYPES = constants('PathTypes', (
    'file',
    'directory',
    'other',
))

EXISTENCES = constants('Existences', dict(
    missing = 0,
    exists = 1,
    exists_case = 2,
))

ANY_EXISTENCE = (EXISTENCES.exists, EXISTENCES.exists_case)

def path_existence_and_type(path):
    # Setup.
    ES = EXISTENCES
    p = Path(path)

    # Determine path existence.
    e = ES.missing
    if p.parent.exists():
        if any(x.name == p.name for x in p.parent.iterdir()):
            # Means p exists and p.name exactly matches the name
            # as reported by file system (including case).
            e = ES.exists_case
        elif p.exists():
            # Means only that p exists.
            e = ES.exists

    # Determine path type and then return.
    pt = None if e is ES.missing else determine_path_type(path)
    return (e, pt)

def determine_path_type(path):
    # Takes a path known to exist.
    # Returns its PATH_TYPES value.
    PTS = PATH_TYPES
    m = os.stat(path, follow_symlinks = False).st_mode
    return (
        PTS.file if stat.S_ISREG(m) else
        PTS.directory if stat.S_ISDIR(m) else
        PTS.other
    )

def is_non_empty_dir(path):
    # Returns true if the given directory path has stuff in it.
    return any(Path(path).iterdir())

####
# Constants and a function to determine file system case sensitivity.
####

FS_TYPES = constants('FileSystemTypes', (
    'case_insensitive',
    'case_preserving',
    'case_sensitive',
))

def case_sensitivity():
    # Determines the file system's case sensitivity.
    # This approach ignore the complexity of per-directory
    # sensitivity settings supported by some operating systems.

    # Return cached value if we have one.
    if case_sensitivity.cached is not None:
        return case_sensitivity.cached

    with TemporaryDirectory() as dpath:
        # Create an empty temp directory.
        # Inside it, touch two differently-cased file names.
        d = Path(dpath)
        f1 = d / 'FoO'
        f2 = d / 'foo'
        f1.touch()
        f2.touch()
        # Ask the file system to report the contents of the temp directory.
        # - If two files, system is case-sensitive.
        # - If the parent reports having 'FoO', case-preserving.
        # - Case-insensitive systems will report having 'foo' or 'FOO'.
        contents = tuple(d.iterdir())
        fs_type = (
            FS_TYPES.case_sensitive if len(contents) == 2 else
            FS_TYPES.case_preserving if contents == (f1,) else
            FS_TYPES.case_insensitive
        )
        case_sensitivity.cached = fs_type
        return fs_type

case_sensitivity.cached = None

####
#
# Failures and Problems.
#
#
# Failures are not specific to a single Renaming and/or have
# no meaningful resolution. Most relate to bad inputs.
#
# Problems are specific to one Renaming. Some of them are resolvable, some not.
# Renamings with unresolvable problems must be skipped/excluded; those with
# resolvable problems can be skipped if the user requests it. Both classes
# have a name, and an optional variety to further classify them.
#
#   Resolvable | Name     | Varieties
#   ----------------------------------------------
#   no         | noop     | equal, same, recase
#   no         | missing  | .
#   no         | type     | .
#   no         | code     | filter, rename
#   no         | exists   | other
#   ----------------------------------------------
#   yes        | exists   | diff, full
#   yes        | collides | diff, full
#   yes        | parent   | .
#
# See command-line help text for more details.
#
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

FAILURE_FORMATS = {
    (FN.all_filtered, None):     'All paths were filtered, excluded, or skipped during processing',
    (FN.parsing, FV.no_paths):   'No input paths',
    (FN.parsing, FV.paragraphs): 'The --paragraphs option expects exactly two paragraphs',
    (FN.parsing, FV.row):        'The --rows option expects rows with exactly two cells: {!r}',
    (FN.parsing, FV.imbalance):  'Got an unequal number of original paths and new paths',
    (FN.code, None):             'Invalid user-supplied {} code:\n{}',
    (FN.strict, None):           'RenamingPlan failed to satisfy strict requirements: {!r}',
}

PROBLEM_NAMES = PN = constants('ProblemNames', (
    'noop',
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

PROBLEM_FORMATS = {
    # Unresolvable.
    (PN.noop, PV.equal):    'Original path and new path are the exactly equal',
    (PN.noop, PV.same):     'Original path and new path are the functionally the same',
    (PN.noop, PV.recase):   'User requested path-name case-change, but file system already agrees with new',
    (PN.missing, None):     'Original path does not exist',
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
        self.__dict__.update(
            name = name,
            variety = variety,
            msg = self.FORMATS[name, variety].format(*xs),
        )

    @property
    def formatted(self):
        return with_newline(self.msg)

@dataclass(init = False, frozen = True)
class Failure(Issue):

    FORMATS = FAILURE_FORMATS

@dataclass(init = False, frozen = True)
class Problem(Issue):

    FORMATS = PROBLEM_FORMATS

    RESOLVABLE = {
        (PN.exists, None),
        (PN.exists, PV.diff),
        (PN.exists, PV.full),
        (PN.collides, None),
        (PN.collides, PV.diff),
        (PN.collides, PV.full),
        (PN.parent, None),
    }

    @classmethod
    def is_resolvable(cls, prob):
        return (prob.name, prob.variety) in cls.RESOLVABLE

    @property
    def sid(self):
        # Resolvable problems have a skip ID, which is just the NAME-VARIETY
        # string that a user provides when declaring which kinds of problems
        # should cause a Renaming to be skipped.
        nm, v = (self.name, self.variety)
        return nm if v is None else f'{nm}-{v}'

    @classmethod
    def from_skip_id(cls, sid):
        # Takes a skip ID.
        # Returns the corresponding Problem or raises.
        xs = underscores_to_hyphens(sid).split(CON.hyphen)
        if len(xs) > 2:
            raise MvsError(MF.invalid_skip, invalid = sid)
        name, variety = (xs + [None])[0:2]
        if (name, variety) in cls.RESOLVABLE:
            return cls(name, variety = variety)
        else:
            raise MvsError(MF.invalid_skip, invalid = sid)

    @classmethod
    def probs_matching_sid(cls, sid):
        # Takes a skip ID.
        # Returns all resolvable problems matching that ID.
        query = cls.from_skip_id(sid)
        return tuple(
            cls(name, variety = variety)
            for name, variety in cls.RESOLVABLE
            if name == query.name and query.variety in (variety, None)
        )

####
# Strict mode.
####

@dataclass(frozen = True)
class StrictMode:
    excluded: bool
    probs: tuple

    EXCLUDED = 'excluded'
    STRICT_PROBS = (PN.parent, PN.exists, PN.collides)

    @classmethod
    def from_user(cls, strict):
        # Convert to tuple.
        err = MvsError(MF.invalid_strict, strict)
        try:
            xs = seq_or_str(strict)
        except Exception:
            raise err
        # Validate and process the tuple values.
        all_strict = False
        excluded = False
        probs = set()
        for x in xs:
            if x == CON.all:
                all_strict = True
            elif x == cls.EXCLUDED:
                excluded = True
            elif x in cls.STRICT_PROBS:
                probs.add(x)
            else:
                raise err
        # Return a StrictMode.
        if all_strict:
            return cls(True, cls.STRICT_PROBS)
        else:
            return cls(excluded, tuple(probs))

    @property
    def as_str(self):
        xs = (
            self.EXCLUDED if self.excluded else None,
            *self.probs,
        )
        return CON.space.join(filter(None, xs))

