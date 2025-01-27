import os
import stat

from pathlib import Path
from short_con import cons
from tempfile import TemporaryDirectory

####
# Path type and existence-status.
####

PATH_TYPES = cons(
    'file',
    'directory',
    'other',
)

EXISTENCES = cons(
    missing = 0,
    exists = 1,
    exists_case = 2,
)

ANY_EXISTENCE = (EXISTENCES.exists, EXISTENCES.exists_case)

def path_existence_and_type(path):
    # Setup.
    ES = EXISTENCES
    p = Path(path)

    # Determine path existence.
    e = ES.missing
    if p.parent.exists():
        if any(sib.name == p.name for sib in p.parent.iterdir()):
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
# File system case sensitivity.
####

FS_TYPES = cons(
    'case_insensitive',
    'case_preserving',
    'case_sensitive',
)

def case_sensitivity():
    # Determines the file system's case sensitivity.
    # This approach ignores the complexity of per-directory
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

