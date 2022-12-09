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
    main()                  # Or ignore this for testing
    pagination              # Ditto
    rename_paths() raises   # Not sure how to test this.

    validated_options() returns a Failure
    check_opts_require_one(): various scenarios

    input paths from:
        clipboard
        file
        stdin

Types of I/O operations in main():

    Writing:
        stdout.write()   # halt()
        stderr.write()   # halt()
        print()          # main(), main(), paginate()
        fh.write()       # log file

    Reading:
        stdin.read()     # collect_input_paths()
        input()          # get_confirmation()

    Pagination:
        subprocess       # paginate()

    Exiting:
        sys.exit()       # halt()

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

def test_bad_indent(tr, capsys):
    origs = ('a', 'b', 'c')
    cli = CliRenamerSIO(
        '--rename',
        'return o + o',
        '--indent',
        '-4',
        *origs,
        file_sys = origs,
    )
    try:
        cli.run()
        cap = None
    except SystemExit as e:
        cap = capsys.readouterr()
    # TODO: rework arg parsing a bit so I can make assert cli.failure instead.
    assert cli.exit_code is None
    exp = '--indent: invalid positive_int value'
    assert exp in cap.err
    assert cap.out == ''

