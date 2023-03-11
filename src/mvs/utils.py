import pyperclip

from dataclasses import dataclass
from kwexception import Kwexception
from pathlib import Path
from short_con import constants
from subprocess import run
from tempfile import gettempdir
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

MSG_FORMATS = constants('MsgFormats', dict(
    # MvsError instances in RenamingPlan.
    rename_done_already    = 'RenamingPlan cannot rename paths because renaming has already been executed',
    prepare_failed         = 'RenamingPlan cannot rename paths because failures occurred during preparation',
    invalid_control        = 'Invalid problem control: {!r}',
    conflicting_controls   = 'Conflicting controls for problem {!r}: {!r} and {!r}',
    invalid_controls       = 'Invalid controls attribute',
    # Error messages in CliRenamer.
    path_collection_failed = 'Collection of input paths failed.\n\n{}',
    plan_creation_failed   = 'Unexpected error during creation of renaming plan.\n\n{}',
    log_writing_failed     = 'Unexpected error during writing to log file.\n\n{}',
    prefs_reading_failed   = 'Unexpected error during reading of user preferences {!r}.\n\n{{}}',
    prepare_failed_cli     = 'Renaming preparation resulted in problems:{}.\n',
    renaming_raised        = '\nRenaming raised an error at tracking_index={}. Traceback follows:\n\n{{}}',
    opts_require_one       = 'One of these options is required',
    opts_mutex             = 'No more than one of these options should be used',
    invalid_pref_val       = 'User preferences: invalid value for {}: expected {}: got {!r}',
    invalid_pref_keys      = 'User preferences: invalid key(s): {}',
    no_editor              = 'The --edit option requires an --editor',
    editor_cmd_nonzero     = 'Editor process exited unsuccessfully: editor={!r}, path={!r}',
    edit_failed_unexpected = 'Editing failed unexpectedly. Traceback follows:\n\n{}',
    # Other messages in CliRenamer.
    paths_to_be_renamed    = 'Paths to be renamed{}.\n',
    confirm_prompt         = '\nRename paths{}',
    no_action_msg          = '\nNo action taken.',
    paths_renamed_msg      = '\nPaths renamed.',
    cli_version_msg        = f'{CON.app_name} v{__version__}',
))

####
# An exception class for the project.
####

class MvsError(Kwexception):
    pass

####
# A dataclass to hold a pair of paths: original and corresponding new.
####

@dataclass(frozen = True)
class RenamePair:
    # A data object to hold an original path and the corresponding new path.
    orig: str
    new: str
    exclude: bool = False
    create_parent: bool = False
    clobber: bool = False

    @property
    def equal(self):
        return self.orig == self.new

    @property
    def formatted(self):
        return f'{self.orig}\n{self.new}\n'

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
    cmd = f"{editor} '{path}'"
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
# Functions given to argparse to validate arguments.
####

def positive_int(x):
    if x.isdigit():
        x = int(x)
        if x >= 1:
            return x
    raise ValueError

####

# A class to hold configuration information for each argparse add_argument()
# call, along with other information used by the mvs library validate
# user-preferences and to merge user-preferences with command-line arguments.


# The preferences checkers return None on success or the expected type
# as a str for use in error messages.
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
# Text wrapping.
####

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

####
# Functions to check path type and existence-status.
####

PATH_TYPES = constants('PathTypes', (
    'file',
    'directory',
    'other',
))

EXISTENCES = constants('Existences', dict(
    missing = 0,
    exists = 1,
    exists_strict = 2,
))

def path_type(path):
    p = Path(path)
    if p.exists():
        return (
            PATH_TYPES.other if p.is_symlink() else
            PATH_TYPES.file if p.is_file() else
            PATH_TYPES.directory if p.is_dir() else
            PATH_TYPES.other
        )
    else:
        # TODO: here.
        return PATH_TYPES.other
        raise MvsError(f'path_type() requires the path to exist', path = path)

def is_valid_path_type(path):
    return path_type(path) in (PATH_TYPES.file, PATH_TYPES.directory)

def paths_have_same_type(path, *others):
    pt = path_type(path)
    return all(pt == path_type(o) for o in others)

def existence_status(path):
    E = EXISTENCES
    p = Path(path)
    if p.parent.exists():
        if p in p.parent.iterdir():
            # Means p exists and p.name exactly matches the name
            # as reported by file system (including case).
            return E.exists_strict
        elif p.exists():
            # Means only that p exists.
            return E.exists
    return E.missing

