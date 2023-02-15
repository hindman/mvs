import json
import os
import pytest
import shutil
import stat

from dataclasses import dataclass
from pathlib import Path

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
    def f(*xs, **kws):
        return Outputs(*xs, **kws)
    return f

####
# General testing resource: data dumping and constants.
####

class TestResource:

    @staticmethod
    def dump(val = None, label = 'dump()'):
        fmt = '\n--------\n{label} =>\n{val}'
        msg = fmt.format(label = label, val = val)
        print(msg)

    @staticmethod
    def dumpj(val = None, label = 'dumpj()', indent = 4):
        val = json.dumps(val, indent = indent)
        self.dump(val, label)

####
# A path within the testing work area.
####

@dataclass(frozen = True, order = True)
class WPath:
    path : str
    is_dir : bool
    mode : str

####
# A class (1) to initialize an empty testing work area, (2) to create file and
# directory paths in that area, and (3) after renaming has occurred, to check
# the resulting work area paths against expectations.
####

class WorkArea:

    ####
    # Constants.
    ####

    SLASH = '/'
    ROOT = f'tests{os.sep}work'
    USER_PERMISSSIONS = {
        'r': stat.S_IRUSR,
        'w': stat.S_IWUSR,
        'x': stat.S_IXUSR,
    }

    ####
    # Creating a WorkArea instance.
    ####

    def __init__(self, origs, news = None, extras = None, expecteds = None):
        # Takes sequences of values, each VAL represents a work area path.
        #
        # - origs : renaming inputs; the original paths.
        # - news : renaming inputs; the new paths.
        # - extras : additional paths to be created in the work area.
        # - expecteds : paths we expect to exist after renaming;
        #   if empty, news + extas is used for this purpose.
        #
        # See to_wpath() for details on the forms that VAL can take.

        # Convert the supplied arguments into tuples of WPath instances.
        self.origs_wp = self.to_wpaths(origs)
        self.news_wp = self.to_wpaths(news)
        self.extras_wp = self.to_wpaths(extras)
        self.expecteds_wp = self.to_wpaths(expecteds)

        # Also store tuples of just the paths as str.
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

        # Unpack the value, which can be either a simple str
        # like 'foo/bar.txt' or a (PATH, MODE) tuple.
        #
        # PATH does not (yet) include the work area root; it
        # uses forward slashes as separators; and it uses trailing
        # slash to indicate that the path should be a directory.
        #
        # MODE is expressed negatively and applies only to user
        # permissions (not group or other). For example: '-wr'
        # means "removes the user write and read permissions"
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

        # If the supplied path ends with a slash, it will be a directory.
        is_dir = path.endswith(self.SLASH)
        path = path.rstrip(self.SLASH)

        # Normalize path and return.
        # - Use os.sep rather than forward slash.
        # - Include the workarea root.
        path = path.replace(self.SLASH, os.sep)
        path = f'{self.ROOT}{os.sep}{path}'
        return WPath(path, is_dir, mode)

    def just_paths(self, wps):
        # Takes some WPath instances. Returns their paths.
        return tuple(wp.path for wp in wps)

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
            if wp.is_dir:
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
        r = self.ROOT
        self.make_subdirs_accessible()
        try:
            shutil.rmtree(r)
        except FileNotFoundError:
            pass
        Path(r).mkdir()

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
    # Checking the work area after renaming has occurred.
    ####

    def check(self, do_assert = True):
        # Actual content of the work area.
        self.make_subdirs_accessible()
        got = sorted(
            str(p)
            for p in Path(self.ROOT).glob('**/*')
        )

        # What we expected.
        wps = self.expecteds_wp or (self.news_wp + self.extras_wp)
        exp = sorted(wp.path for wp in wps)

        # Assert and return.
        if do_assert:
            assert got == exp
        return (got, exp)

class Outputs:

    def __init__(self, origs, news, total = None, listed = None):
        self.origs = origs
        self.news = news
        self.total = len(origs) if total is None else total
        self.listed = self.total if listed is None else listed

    @property
    def totlist(self):
        return f'(total {self.total}, listed {self.listed})'

    @property
    def paths_to_be_renamed(self):
        args = [f'Paths to be renamed {self.totlist}.\n']
        args.extend(
            f'{o}\n{n}\n'
            for o, n in zip(self.origs, self.news)
        )
        return '\n'.join(args) + '\n'

    @property
    def confirm(self):
        return f'Rename paths {self.totlist} [yes]? \n'

    @property
    def paths_renamed(self):
        return 'Paths renamed.\n'

    @property
    def no_action(self):
        return 'No action taken.\n\n'

