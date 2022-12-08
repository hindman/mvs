import pytest
import io
import re

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
    parse_command_line_args,
)

'''

TODO:
    if plan.failed: the true scenario
    dryrun
    user says no to confirmation
    rename_paths() raises
    validated_options() returns a Failure
    check_opts_require_one(): various scenarios
    input paths from:
        clipboard
        file
        stdin

Where I/O happens:

    Writing output:

        - Use capsys

        sys.stderr.write()  # halt()
        sys.stdout.write()  # halt()
        print()             # paginate(); main() twice
        input()             # get_confirmation()

    Exiting:
        - Catch SystemExit.

        sys.exit()          # halt()

    Getting user input:

        sys.stdin.read()    # collect_input_paths()
        input()             # get_confirmation()

'''

def test_version_and_help(tr, capsys):
    # Version.
    args = ('bmv', '--version')
    with pytest.raises(SystemExit) as exc:
        main(args)
    assert exc.value.code == CON.exit_ok
    cap = capsys.readouterr()
    assert cap.out == f'{CON.app_name} v{__version__}\n'
    assert cap.err == ''

    # Help.
    args = ('bmv', '--version', '--help')
    with pytest.raises(SystemExit) as exc:
        main(args)
    assert exc.value.code == CON.exit_ok
    cap = capsys.readouterr()
    out = cap.out
    assert cap.err == ''
    assert out.startswith(f'Usage: {CON.app_name}')
    assert len(out) > 4000
    for opt in ('--clipboard', '--paragraphs', '--rename'):
        assert f'\n  {opt}' in out

def glob(pattern, root = '.'):
    return tuple(map(str, Path(root).glob(pattern)))

def test_main_basic(tr, capsys, monkeypatch):
    args = tr.cliargs('--rename', 'return o + o')
    origs = ('a', 'b', 'c')
    file_sys = origs
    exp_file_sys = ('aa', 'bb', 'cc')
    monkeypatch.setattr('sys.stdin', io.StringIO('yes'))
    plan = main(args + origs, file_sys = file_sys)
    assert tuple(plan.file_sys) == exp_file_sys
    cap = capsys.readouterr()
    assert cap.err == ''
    got = re.sub(r' +\n', '\n', cap.out)
    exp = dedent('''
        Paths to be renamed (total 3, listed 3).

        a
        aa

        b
        bb

        c
        cc


        Rename paths (total 3, listed 3) [yes]?
        Paths renamed.
    ''').lstrip()
    assert got == exp

def test_main_prepare_failed(tr, capsys, monkeypatch):
    origs = ('z1',)
    args = tr.cliargs()
    with pytest.raises(SystemExit) as exc:
        main(args + origs, file_sys = origs)
    assert exc.value.code == CON.exit_fail
    cap = capsys.readouterr()
    assert cap.out == ''
    assert cap.err == 'Renaming preparation failed: Got an unequal number of original paths and new paths.\n'

