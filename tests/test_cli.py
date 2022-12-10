import pytest
import re

from io import StringIO
from pathlib import Path
from textwrap import dedent
from string import ascii_lowercase

from bmv.constants import (
    CON,
    FAIL,
    STRUCTURES,
)

from bmv.version import __version__

from bmv.cli import (
    main,
    CliRenamer,
    write_to_clipboard,
)

'''

TODO:

    scenario with some failed rps in the listing.

        plan.uncontrolled_failures now contains WrappedFailure instances.

        See test_some_failed_rps() to continue this scenario

        but there is a new problem: cannot JSONify a WrappedFailure

    scenario with some invalid failure controls via the CliRenamer

    scenario with too few/many sources and structures via the CliRenamer

    Then refactor validated_options()into one function.

    Now that CliRenamer exists, handle_exit() seems out of place: remove?

'''

class CliRenamerSIO(CliRenamer):
    # A thin wrapper around a CliRenamer using StringIO instances:
    #
    # - Adds args to disable pagination by default.
    # - Sets I/O handles to be StringIO instances, so we can capture outputs.
    # - Adds a convenience (yes) to simulate user confirmation.
    # - Adds a convenience (replies) to feed stdin.
    # - Adds a few properties/methods to simplify assertion making.

    def __init__(self, *args, file_sys = None, replies = '', yes = False, pager = ''):
        args = args + ('--pager', pager)
        super().__init__(
            args,
            file_sys = file_sys,
            stdout = StringIO(),
            stderr = StringIO(),
            stdin = StringIO('yes' if yes else replies),
            logfh = StringIO(),
        )

    @property
    def success(self):
        return self.exit_code == CON.exit_ok

    @property
    def failure(self):
        return self.exit_code == CON.exit_fail

    @property
    def out(self):
        return self.stdout.getvalue()

    @property
    def err(self):
        return self.stderr.getvalue()

    @property
    def log(self):
        return self.logfh.getvalue()

    def check_file_sys(self, *paths):
        assert tuple(self.plan.file_sys) == paths

def test_version_and_help(tr):
    # Version.
    cli = CliRenamerSIO('bmv', '--version')
    cli.run()
    assert cli.success
    assert cli.err == ''
    assert cli.out == f'{CON.app_name} v{__version__}\n'

    # Help.
    cli = CliRenamerSIO('bmv', '--version', '--help')
    cli.run()
    assert cli.success
    assert cli.err == ''
    assert cli.out.startswith(f'Usage: {CON.app_name}')
    assert len(cli.out) > 4000
    for opt in ('--clipboard', '--paragraphs', '--rename'):
        assert f'\n  {opt}' in cli.out

def test_basic_use_case(tr):
    origs = ('a', 'b', 'c')
    cli = CliRenamerSIO(
        '--rename',
        'return o + o',
        *origs,
        file_sys = origs,
        yes = True,
    )
    cli.run()
    assert cli.success
    cli.check_file_sys('aa', 'bb', 'cc')
    assert cli.err == ''
    got = cli.out.replace(' \n', '\n\n', 1)
    exp = tr.OUTS['listing_a2aa'] + tr.OUTS['confirm3'] + tr.OUTS['paths_renamed']
    assert got == exp

def test_prepare_failed(tr):
    origs = ('z1',)
    cli = CliRenamerSIO(*origs, file_sys = origs)
    cli.run()
    assert cli.failure
    assert cli.out == ''
    assert cli.err == 'Renaming preparation resulted in failures: (total 1, listed 1).\n\nGot an unequal number of original paths and new paths\n'

def test_dryrun(tr):
    origs = ('a', 'b', 'c')
    cli = CliRenamerSIO(
        '--rename',
        'return o + o',
        '--dryrun',
        *origs,
        file_sys = origs,
    )
    cli.run()
    assert cli.success
    cli.check_file_sys(*origs)
    assert cli.err == ''
    got = re.sub(r' +\n', '\n', cli.out)
    exp = tr.OUTS['listing_a2aa'] + tr.OUTS['no_action']
    assert got == exp

def test_no_confirmation(tr):
    origs = ('a', 'b', 'c')
    cli = CliRenamerSIO(
        '--rename',
        'return o + o',
        *origs,
        file_sys = origs,
    )
    cli.run()
    assert cli.success
    assert cli.err == ''
    cli.check_file_sys(*origs)
    got = cli.out.replace(' \n', '\n\n', 1)
    exp = tr.OUTS['listing_a2aa'] + tr.OUTS['confirm3'] + tr.OUTS['no_action']
    assert got == exp

def test_indent_and_posint(tr):
    # Paths and args.
    origs = ('a', 'b', 'c')
    args = ('--rename', 'return o + o', '--indent')
    exp_file_sys = ('aa', 'bb', 'cc')

    # Valid indent values.
    for i in ('2', '4', '8'):
        cli = CliRenamerSIO(*args, i, *origs, file_sys = origs, yes = True)
        cli.run()
        assert cli.success
        cli.check_file_sys(*exp_file_sys)
        assert cli.err == ''
        assert cli.out

    # Invalid indent values.
    for i in ('-4', 'xx', '0', '1.2'):
        cli = CliRenamerSIO(*args, i, *origs, file_sys = origs, yes = True)
        cli.run()
        assert cli.failure
        assert cli.out == ''
        exp = '--indent: invalid positive_int value'
        assert exp in cli.err
        assert cli.err.startswith(f'usage: {CON.app_name}')

def test_rename_paths_raises(tr):
    # Paths and args.
    origs = ('z1', 'z2')
    news = ('z1x', 'z2x')
    args = origs + news + ('--yes',)

    # A working scenario.
    cli = CliRenamerSIO(*args, file_sys = origs)
    cli.run()
    assert cli.success
    cli.check_file_sys(*news)

    # Same thing, but using do_prepare() and do_rename().
    cli = CliRenamerSIO(*args, file_sys = origs)
    cli.do_prepare()
    cli.do_rename()
    assert cli.success
    cli.check_file_sys(*news)

    # Same thing. Calling the methods multiple times has no effect.
    cli = CliRenamerSIO(*args, file_sys = origs)
    cli.do_prepare()
    cli.do_prepare()
    cli.do_rename()
    cli.do_rename()
    assert cli.success
    cli.check_file_sys(*news)

    # Same thing, but we will set plan.has_renamed to trigger an exception
    # when plan.rename_paths() is called.
    cli = CliRenamerSIO(*args, file_sys = origs)
    cli.do_prepare()
    cli.plan.has_renamed = True
    cli.do_rename()
    assert cli.failure
    assert cli.err.strip().startswith('Renaming raised an error')
    assert 'raise BmvError(FAIL.rename_done_already)' in cli.err

def test_sources(tr):
    # Paths and args.
    origs = ('z1', 'z2', 'z3')
    news = ('A1', 'A2', 'A3')
    args = origs + news
    args_txt = CON.newline.join(args)
    yes = '--yes'

    def do_checks(cli):
        cli.run()
        assert cli.success
        cli.check_file_sys(*news)

    # Base scenario: paths via args.
    cli = CliRenamerSIO(*args, yes, file_sys = origs)
    do_checks(cli)

    # Paths via clipboard.
    write_to_clipboard(args_txt)
    cli = CliRenamerSIO('--clipboard', yes, file_sys = origs)
    do_checks(cli)

    # Paths via stdin.
    cli = CliRenamerSIO('--stdin', yes, file_sys = origs, replies = args_txt)
    do_checks(cli)

    # Paths via a file.
    path = tr.TEMP_PATH
    with open(path, 'w') as fh:
        fh.write(args_txt)
    cli = CliRenamerSIO('--file', path, yes, file_sys = origs, replies = args_txt)
    do_checks(cli)

def test_pagination(tr):
    # Paths.
    origs = tuple(ascii_lowercase)
    news = tuple(o + o for o in origs)

    # Exercise the paginate() function by using cat and /dev/null.
    cli = CliRenamerSIO(
        *origs,
        '--rename',
        'return o + o',
        file_sys = origs,
        yes = True,
        pager = 'cat > /dev/null',
    )
    cli.run()
    assert cli.success
    cli.check_file_sys(*news)

def test_some_failed_rps(tr):
    # Paths and args.
    origs = ('z1', 'z2', 'z3', 'z4')
    news = ('A1', 'z2', 'z3', 'A4')
    args = origs + news

    # Initial scenario fails: orig and new paths are the same.
    cli = CliRenamerSIO(
        *args,
        file_sys = origs,
        yes = True,
    )
    cli.run()
    assert cli.failure
    assert cli.err.startswith('Renaming preparation resulted in failures: (total 2, listed 2)')
    assert 'Original path and new path are the same' in cli.err

    # TODO
    # WrappedFailure is not JSON serializable.
    return

    # Initial scenario fails: orig and new paths are the same.
    cli = CliRenamerSIO(
        *args,
        '--skip-equal',
        file_sys = origs,
        yes = True,
    )
    cli.run()
    assert cli.success
    cli.check_file_sys(news[0], news[-1])

