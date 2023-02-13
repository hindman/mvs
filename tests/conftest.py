import json
import os
import pytest
import shutil
import stat

from dataclasses import dataclass
from pathlib import Path
from textwrap import dedent

@pytest.fixture
def tr():
    return TestResource()

@pytest.fixture
def wa():
    return WorkArea()

class TestResource(object):

    ####
    # Expected outputs during command-line usage.
    ####

    OUTS = dict(
        listing_a2aa = dedent('''
            Paths to be renamed (total 3, listed 3).

            a
            aa

            b
            bb

            c
            cc

        ''').lstrip(),
        confirm3 = dedent('''
            Rename paths (total 3, listed 3) [yes]?

        ''').lstrip(),
        paths_renamed = dedent('''
            Paths renamed.
        ''').lstrip(),
        no_action = dedent('''
            No action taken.
        ''').lstrip(),
    )

    ####
    # Helper to set up the work area with various paths.
    ####

    # def temp_area(self, origs, news, extras = ()):
    #     # Initialize an empty work area.
    #     wa = self.WORK_AREA_ROOT
    #     shutil.rmtree(wa, ignore_errors = True)
    #     Path(wa).mkdir()
    #     # Add work area prefix to the paths.
    #     wp = lambda p: f'{wa}/{p}'
    #     origs = tuple(map(wp, origs))
    #     news = tuple(map(wp, news))
    #     extras = tuple(map(wp, extras))
    #     # Put original paths (plus any extras) in the work area.
    #     for p in origs + extras:
    #         if p.endswith('/'):
    #             Path(p).mkdir()
    #         else:
    #             Path(p).touch()
    #     # Return the prefixed paths.
    #     if extras:
    #         return (origs, news, extras)
    #     else:
    #         return (origs, news)

    ####
    # Data dumping.
    ####

    def dump(self, val = None, label = 'dump()'):
        fmt = '\n--------\n{label} =>\n{val}'
        msg = fmt.format(label = label, val = val)
        print(msg)

    def dumpj(self, val = None, label = 'dump()', indent = 4):
        val = json.dumps(val, indent = indent)
        self.dump(val, label)

class WorkArea(object):
    '''

    Constants from stat.

        owner:
        S_IRUSR  (00400)  read
        S_IWUSR  (00200)  write
        S_IXUSR  (00100)  execute

        group:
        S_IRGRP  (00040)  read
        S_IWGRP  (00020)  write
        S_IXGRP  (00010)  execute

        others:
        S_IROTH  (00004)  read
        S_IWOTH  (00002)  write
        S_IXOTH  (00001)  execute

        4 read
        2 write
        1 execute

        Digits: owner, group, others.

        -rw-r--r--  File  644
        drwxr-xr-x  Dir   755

    Changing owner requires sudo, so will be a hassle in tests.

    The primary way to cause a rename failure is to make the parent dir non-writable.
    And you only need to do it for the user.

    This example will change a file's permissions in the fashion of chmod u-w

       mode = os.stat(path).st_mode
       os.chmod(path, mode ^ stat.S_IWUSR)

    More generally, one could support removing the current user's
    read, write, or execute: -r -w -x

    '''

    ####
    # Paths in the testing work area used to exercise
    # the command-line functionality end-to-end.
    ####

    SLASH = '/'

    ROOT = f'tests{os.sep}work'

    USER_PERMISSSIONS = {
        'r': stat.S_IRUSR,
        'w': stat.S_IWUSR,
        'x': stat.S_IXUSR,
    }

    def __init__(self):
        self.origs = None
        self.news = None
        self.extras = None
        self.expecteds = None

    def create(self, origs, news = None, extras = None, expecteds = None):
        # Initialize an empty work area.
        self.initialize()

        # Convert the supplied arguments into tuples of WPath instances.
        self.origs = self.to_wpaths(origs)
        self.news = self.to_wpaths(news)
        self.extras = self.to_wpaths(extras)
        self.expecteds = self.to_wpaths(expecteds)

        # Put origs and extra in the work area.
        to_create = self.origs + self.extras
        for wp in to_create:
            p = Path(wp.path)
            if wp.is_dir:
                p.mkdir()
            else:
                p.touch()

        # Remove permissions. We do it in reverse order so that the permissions
        # of children will be removed before those of parents.
        for wp in sorted(to_create, reverse = True):
            self.remove_permissions(wp)

        result = tuple(
            tuple(wp.path for wp in wps)
            for wps in (self.origs, self.news, self.extras)
        )
        if self.extras:
            return result
        else:
            return result[0:2]

    def initialize(self):
        # Creates an empty work area.
        r = self.ROOT
        try:
            shutil.rmtree(r)
        except FileNotFoundError:
            pass
        except Exception:
            self.make_subdirs_accessible(r)
            shutil.rmtree(r)
        Path(r).mkdir()

    def to_wpaths(self, xs):
        # Takes a sequence supplied to create().
        # Returns a tuple of WPath.
        if xs is None:
            return ()
        else:
            return tuple(self.to_wpath(x) for x in xs)

    def to_wpath(self, x):
        # Takes one value from a sequence supplied to create().
        # Returns a WPath.

        # Unpack the value.
        # Note that WPath.mode is expressed negatively.
        # Example: '-wr' means "removes the user write and read permissions"
        if isinstance(x, tuple):
            path, mode = x
            if not mode.startswith('-'):
                raise ValueError(f'Invalid WPath mode: {mode}')
        else:
            path = x
            mode = None

        # If the supplied path ends with a slash, it will be a directory.
        is_dir = path.endswith(self.SLASH)
        path.rstrip(self.SLASH)

        # Normalize path:
        # - Use os.sep rather than forward slash.
        # - Include the workarea root.
        path = path.replace(self.SLASH, os.sep)
        path = f'{self.ROOT}{os.sep}{path}'

        # Return a WPath.
        return WPath(path, is_dir, mode)

    def remove_permissions(self, wp):
        # Takes a WPath. If it has a mode, executes
        # a chmod to remove one or more user permissions.
        if wp.mode:
            curr = os.stat(wp.path).st_mode
            mask = self.compute_mask(wp.mode)
            os.chmod(wp.path, curr ^ mask)

    def compute_mask(self, wp_mode):
        # Helper for remove_permissions().
        mask = 0
        for k, val in self.USER_PERMISSSIONS.items():
            if k in wp_mode:
                mask = mask | val
        return mask

    def make_subdirs_accessible(self, root):
        # Helper used when the first attempt to clear out the work area fails
        # because a prior test made some subdirs non-accessible. It traverses
        # the tree, calling chmod on every subdir.
        todo = [Path(root)]
        while todo:
            p = todo.pop()
            for kid in p.iterdir():
                if kid.is_dir():
                    self.make_dir_accessible(kid)
                    todo.append(kid)

    def make_dir_accessible(self, p):
        # Takes a Path of a directory.
        # Makes it fully accessible: read, write, execute.
        curr = p.stat().st_mode
        mask = self.compute_mask('rwx')
        p.chmod(curr | mask)

    def check(self):

        # Read the work area contents.
        # Will I need to call make_subdirs_accessible()??
        pass

        # Compare it to expectation.
        exp = self.expecteds or self.news

@dataclass(frozen = True, order = True)
class WPath:
    path : str
    is_dir : bool
    mode : str

