import pytest
import re

from io import StringIO
from pathlib import Path
from textwrap import dedent

from bmv.constants import (
    CON,
    FAIL,
    STRUCTURES,
)

from bmv.version import __version__

from bmv.cli import (
    main,
    CliRenamer,
)

'''

TODO:
    main()                  # Ignore?

    rename_paths() raises   # Test by setting plan.has_renamed = True

    pagination              # Ignore?

    input paths from:
        clipboard
        file
        stdin

    scenario with some failed rps in the listing.

    scenario with some invalid failure controls via the CliRenamer

    scenario with too few/many sources and structures via the CliRenamer

    Then refactor validated_options()into one function.

'''

class CliRenamerSIO(CliRenamer):
    # A thin wrapper around a CliRenamer using StringIO instances:
    #
    # - Adds args to disable pagination.
    # - Sets I/O handles to be StringIO instances, so we can capture outputs.
    # - Add a convenience for user confirmation.
    # - Adds a few properties/methods to simplify assertion making.

    def __init__(self, *args, file_sys = None, reply = '', yes = False):
        args = args + ('--pager', '')
        super().__init__(
            args,
            file_sys = file_sys,
            stdout = StringIO(),
            stderr = StringIO(),
            stdin = StringIO('yes' if yes else reply),
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

def test_version_and_help(tr, capsys):
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
    assert cli.err == 'Renaming preparation failed: Got an unequal number of original paths and new paths.\n'

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

