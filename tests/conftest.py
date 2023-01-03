import json
import pytest
import shutil

from textwrap import dedent
from pathlib import Path

@pytest.fixture
def tr():
    return TestResource()

class TestResource(object):

    ####
    # Paths in the testing work area used to exercise
    # the command-line functionality end-to-end.
    ####

    WORK_AREA_ROOT = 'tests/work_area'
    TEMP_PATH = f'{WORK_AREA_ROOT}/tempfile'

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

    def temp_area(self, origs, news, extras = ()):
        # Initialize an empty work area.
        wa = self.WORK_AREA_ROOT
        shutil.rmtree(wa, ignore_errors = True)
        Path(wa).mkdir()
        # Add work area prefix to the paths.
        wp = lambda p: f'{wa}/{p}'
        origs = tuple(map(wp, origs))
        news = tuple(map(wp, news))
        extras = tuple(map(wp, extras))
        # Put original paths (plus any extras) in the work area.
        for p in origs + extras:
            if p.endswith('/'):
                Path(p).mkdir()
            else:
                Path(p).touch()
        # Return the prefixed paths.
        if extras:
            return (origs, news, extras)
        else:
            return (origs, news)

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

