import subprocess

from dataclasses import dataclass
from kwexception import Kwexception
from short_con import constants
from textwrap import dedent

####
# Constants.
####

# Structures for input paths data.
STRUCTURES = constants('Structures', (
    'paragraphs',
    'flat',
    'pairs',
    'rows',
))

# Message formats.
MSG_FORMATS = constants('MsgFormats', dict(
    # BmvError instances in RenamingPlan.
    rename_done_already    = 'RenamingPlan cannot rename paths because renaming has already been executed',
    prepare_failed         = 'RenamingPlan cannot rename paths because failures occurred during preparation',
    invalid_control        = 'Invalid problem name(s) for {!r} control: {}',
    conflicting_controls   = 'Conflicting controls for problem {!r}: {!r} and {!r}',
    invalid_file_sys       = 'Plan.file_sys must be None or an iterable',
    # Error messages in CliRenamer.
    path_collection_failed = 'Collection of input paths failed.\n\n{}',
    plan_creation_failed   = 'Unexpected error during creation of renaming plan.\n\n{}',
    log_writing_failed     = 'Unexpected error during writing to log file.\n\n{}',
    prepare_failed_cli     = 'Renaming preparation resulted in failures:{}.\n',
    renaming_raised        = '\nRenaming raised an error; some paths might have been renamed; traceback follows:\n\n{}',
    opts_require_one       = 'One of these options is required',
    opts_mutex             = 'No more than one of these options should be used',
    # Other messages in CliRenamer.
    no_action_msg          = '\nNo action taken.',
    paths_renamed_msg      = '\nPaths renamed.',
))

class CON:
    # General constants.

    # Application configuration.
    app_name = 'bmv'
    encoding = 'utf-8'

    # Characters and simple tokens.
    newline = '\n'
    tab = '\t'
    underscore = '_'
    hyphen = '-'
    dash = hyphen + hyphen
    all = 'all'
    all_tup = (all,)

    # User-supplied code.
    user_code_fmt = 'def {func_name}(o, p, seq, plan):\n{indent}{user_code}\n'
    renamer_name = '_do_rename'
    filterer_name = '_do_filter'

    # Command-line exit codes.
    exit_ok = 0
    exit_fail = 1

    # Other executables.
    default_pager_cmd = 'more'
    default_copy_cmd = 'pbcopy'
    default_paste_cmd = 'pbpaste'

####
# An exception class for the project.
####

class BmvError(Kwexception):
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

def read_from_clipboard():
    cp = subprocess.run(
        [CON.default_paste_cmd],
        capture_output = True,
        check = True,
        text = True,
    )
    return cp.stdout

def write_to_clipboard(text):
    subprocess.run(
        [CON.default_copy_cmd],
        check = True,
        text = True,
        input = text,
    )

####
# Other.
####

def positive_int(x):
    # Helper for argparse configuration to check for positive integers.
    if x.isdigit():
        x = int(x)
        if x >= 1:
            return x
    raise ValueError

