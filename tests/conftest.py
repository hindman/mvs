import json
import os
import pytest
import shutil
import stat
import os

from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from mvs.utils import CON, MSG_FORMATS as MF

####
# Set the mvs environment variable so that (1) the user's personal
# mvs preferences file won't be used during testing and (2) so
# that we can exercise the preferences in various ways.
#
# We set it to the full (rather than relative) path because some tests
# using a WorkArea change the working directory before renaming occurs.
####

APP_DIR_FOR_TESTING = str(Path().resolve() / 'tests/mvs_app')

os.environ[CON.app_dir_env_var] = APP_DIR_FOR_TESTING

####
# Fixtures.
####

@pytest.fixture
def tr():
    return TestResource()

@pytest.fixture
def create_wa():
    def f(*xs, **kws):
        wa = WorkArea(*xs, **kws)
        wa.create()
        return wa
    return f

@pytest.fixture
def create_outs():
    return Outputs

@pytest.fixture
def create_prefs():
    def f(**kws):
        up = UserPrefs(**kws)
        up.create()
        return up
    yield f
    UserPrefs.delete()

@pytest.fixture
def creators(create_wa, create_outs, create_prefs):
    return (create_wa, create_outs, create_prefs)

####
# General testing resource: data dumping and constants.
####

class TestResource:

    TEST_EDITOR = 'python tests/editor.py'
    TEST_PAGER = 'python tests/empty-pager.py'
    TEST_FAILER = 'python tests/failer.py'

    @classmethod
    def dump(cls, val = None, label = 'dump()'):
        fmt = '\n--------\n# {label} =>\n{val}'
        msg = fmt.format(label = label, val = val)
        print(msg)

    @classmethod
    def dumpj(cls, val = None, label = 'dumpj()', indent = 4):
        val = json.dumps(val, indent = indent)
        cls.dump(val, label)

    @staticmethod
    def msg_before_formatting(fmt):
        # Takes a format string.
        # Returns the portion before the first brace.
        return fmt.split('{')[0]

####
# A path within the testing work area.
####

@dataclass(frozen = True, order = True)
class WPath:
    path : str
    is_dir : bool
    mode : str
    target : str

    @property
    def is_link(self):
        return self.target is not None

####
# A class used by the create_wa() fixture (1) to initialize an empty testing
# work area, (2) to create file and directory paths in that area, and (3) after
# renaming has occurred, to check the resulting work area paths against
# expectations.
####

class WorkArea:

    ####
    # Constants.
    ####

    SLASH = '/'
    LINK_SEP = '->'
    ROOT = f'tests{os.sep}work'
    KEEP_FILE = '.keep'
    USER_PERMISSSIONS = {
        'r': stat.S_IRUSR,
        'w': stat.S_IWUSR,
        'x': stat.S_IXUSR,
    }

    ####
    # Creating a WorkArea instance.
    ####

    def __init__(self,
                 origs,
                 news = None,
                 extras = None,
                 expecteds = None,
                 rootless = False):
        # Takes sequences of values, each VAL represents a work area path.
        #
        # - origs : renaming inputs; the original paths.
        # - news : renaming inputs; the new paths.
        # - extras : additional paths to be created in the work area.
        # - expecteds : paths we expect to exist after renaming;
        #   if empty, news + extas is used for this purpose.
        #
        # See to_wpath() for details on the forms that VAL can take.

        # Rootless mode.
        self.rootless = rootless

        # Convert the supplied arguments into tuples of WPath instances. These
        # are the attributes used by WorkArea to manage its own affairs, such
        # as creating paths and checking final work area contents. These paths
        # are expressed relative to the repository root.
        self.origs_wp = self.to_wpaths(origs)
        self.news_wp = self.to_wpaths(news)
        self.extras_wp = self.to_wpaths(extras)
        self.expecteds_wp = self.to_wpaths(expecteds)

        # Also store tuples of just the paths as str. These are attributes used
        # by the caller to pass inputs into a RenamingPlan. Depending on the
        # value of rootless, these paths might or might not have the work area
        # ROOT as a prefix. In rootless mode, the caller intends to execute
        # rename_paths() from the work area root (not repo root).
        self.origs = self.just_paths(self.origs_wp)
        self.news = self.just_paths(self.news_wp)
        self.extras = self.just_paths(self.extras_wp)
        self.expecteds = self.just_paths(self.expecteds_wp)

    def to_wpaths(self, xs):
        # Takes a sequence supplied to WorkArea().
        # Returns a tuple of WPath.
        if xs:
            return tuple(self.to_wpath(x) for x in xs)
        else:
            return ()

    def to_wpath(self, x):
        # Takes one value from a sequence supplied to WorkArea().
        # Returns a WPath.
        #
        # The value can be:
        # - str: 'foo/bar.txt'
        # - tuple: (PATH, MODE)
        #
        # The PATH value:
        # - Does not (yet) include the work area root.
        # - Uses forward slashes as separators.
        # - Uses trailing slash to indicate that path should be a directory.
        # - Uses an arrow to indicate a symlink: 'PATH->TARGET'.
        #
        # The MODE value:
        # - Is expressed negatively.
        # - Applies only to user permissions (not group or other).
        # - Example: '-wr' means "removes the user write and read permissions".
        #

        # Unpack the path and mode.
        if isinstance(x, tuple):
            path, mode = x
            mode_ok = (
                mode.startswith('-') and
                all(char in '-rwx' for char in mode)
            )
            if not mode_ok:
                raise ValueError(f'Invalid WPath mode: {mode}')
        else:
            path = x
            mode = None

        if self.LINK_SEP in path:
            path, target = path.split(self.LINK_SEP, 1)
            is_dir = False
        else:
            # If the supplied path ends with a slash, it will be a directory.
            is_dir = path.endswith(self.SLASH)
            path = path.rstrip(self.SLASH)
            target = None

        # Normalize path and return.
        # - Use os.sep rather than forward slash.
        # - Include the workarea root.
        path = path.replace(self.SLASH, os.sep)
        path = self.prefix + path
        return WPath(path, is_dir, mode, target)

    def just_paths(self, wps):
        # Takes some WPath instances. Returns their paths.
        # Those paths might or might not include the ROOT prefix.
        i = len(self.prefix) if self.rootless else 0
        return tuple(wp.path[i:] for wp in wps)

    @property
    def prefix(self):
        return self.ROOT + os.sep

    ####
    # Creating the paths in the work area.
    ####

    def create(self):
        # Initialize an empty work area.
        self.initialize()

        # Put origs and extras in the work area.
        to_create = self.origs_wp + self.extras_wp
        for wp in to_create:
            p = Path(wp.path)
            if wp.is_link:
                p.symlink_to(wp.target)
            elif wp.is_dir:
                p.mkdir()
            else:
                p.parent.mkdir(parents = True, exist_ok = True)
                p.touch()

        # Remove permissions. We do it in reverse order so that the permissions
        # of children will be removed before those of parents.
        for wp in sorted(to_create, reverse = True):
            self.remove_permissions(wp)

    def initialize(self):
        # Creates an empty work area.

        # Make the directory tree fully accessible.
        r = self.ROOT
        self.make_subdirs_accessible()

        # Remove the directory.
        try:
            shutil.rmtree(r)
        except FileNotFoundError:
            pass

        # Create directory and KEEP_FILE.
        p = Path(r)
        p.mkdir()
        k = p / self.KEEP_FILE
        k.touch()

    def make_subdirs_accessible(self):
        # Helper used before we need to traverse the work area.
        # Makes every directory in it fully accessible (rwx).
        todo = [Path(self.ROOT)]
        while todo:
            p = todo.pop()
            for kid in p.iterdir():
                if kid.is_dir():
                    self.make_dir_accessible(kid)
                    todo.append(kid)

    def make_dir_accessible(self, p):
        # Takes directory as a Path. Makes it fully accessible.
        curr = p.stat().st_mode
        mask = self.compute_mask('rwx')
        p.chmod(curr | mask)

    def compute_mask(self, wp_mode):
        # Helper when modifying path permissions.
        # Takes a WPath mode value. Returns corresponding
        # values after combining them with bitwise-OR.
        mask = 0
        for k, val in self.USER_PERMISSSIONS.items():
            if k in wp_mode:
                mask = mask | val
        return mask

    def remove_permissions(self, wp):
        # Takes a WPath. If it has a mode, executes
        # a chmod to remove one or more user permissions.
        if wp.mode:
            curr = os.stat(wp.path).st_mode
            mask = self.compute_mask(wp.mode)
            os.chmod(wp.path, curr ^ mask)

    ####
    # Change directory to the work area root.
    ####

    @contextmanager
    def cd(self):
        prev = os.getcwd()
        os.chdir(self.ROOT)
        try:
            yield
        finally:
            os.chdir(prev)

    ####
    # Checking the work area after renaming has occurred.
    ####

    def check(self, do_assert = True, no_change = False):
        # What we expect to find.
        #
        # Note the this logic is too simple for situations
        # where the input paths in WorkArea contain subdirectories.
        # So far, there are not too many tests where this kind
        # of scenario is used, and it has been handled via
        # an explicit declaration of expecteds.
        if self.expecteds_wp:
            wps = self.expecteds_wp
        elif no_change:
            wps = self.origs_wp + self.extras_wp
        else:
            wps = self.news_wp + self.extras_wp
        exp = sorted(set(wp.path for wp in wps))

        # Actual content of the work area (other than KEEP_FILE).
        keep = Path(self.ROOT) / self.KEEP_FILE
        self.make_subdirs_accessible()
        got = sorted(
            str(p)
            for p in Path(self.ROOT).glob('**/*')
            if p != keep
        )

        # Assert and return.
        if do_assert:
            assert got == exp
        return (got, exp)

####
# A class used by the create_outs() fixture to take orig and new paths
# inside a WorkArea and return expected CliRenamer outputs.
####

class Outputs:

    SUMMARY_KEYS = (
        'n_initial',
        'n_active',
        'n_filtered',
        'n_skipped',
        'n_create',
        'n_clobber',
    )

    def __init__(self, origs, news, total = None, summary = None):
        self.origs = origs
        self.news = news
        self.total = len(origs) if total is None else total
        self.summary = None
        if summary:
            kws = dict(zip(self.SUMMARY_KEYS, summary))
            self.summary = MF.summary_table.format(**kws) + CON.newline

    @property
    def totlist(self):
        return f'(total {self.total})'

    @property
    def regular_output(self):
        return ''.join((
            self.summary or '',
            self.listing_rename,
            self.paths_renamed,
        ))

    @property
    def no_action_output(self):
        return self.listing_rename + self.no_action

    @property
    def no_confirm_output(self):
        return self.listing_rename + self.confirm + self.no_action

    @property
    def listing_rename(self):
        args = [f'Paths to be renamed {self.totlist}:\n']
        args.extend(
            f'{o}\n{n}\n'
            for o, n in zip(self.origs, self.news)
        )
        return '\n'.join(args) + '\n'

    @property
    def confirm(self):
        return f'Rename paths [yes]? \n'

    @property
    def paths_renamed(self):
        return 'Paths renamed.\n'

    @property
    def no_action(self):
        return 'No action taken.\n'

####
# A class used by the create_prefs() fixture to (1) write a user-preferences
# file for use in testing and (2) delete that file after a test finished.
#
#
# In regular use, it writes its keyword params as JSON.
#
# If given a blob (of presumably invalid JSON), it is
# written directly.
####

class UserPrefs:

    PATH = Path(APP_DIR_FOR_TESTING) / CON.prefs_file_name

    def __init__(self, blob = None, **kws):
        self.blob = blob
        self.params = kws

    def create(self):
        with open(self.PATH, 'w') as fh:
            if self.blob is None:
                json.dump(self.params, fh, indent = 4)
            else:
                fh.write(self.blob)

    @classmethod
    def delete(cls):
        try:
            cls.PATH.unlink()
        except FileNotFoundError:
            pass

