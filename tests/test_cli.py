import pytest
import io
from pathlib import Path

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
    prepare() fails
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

def test_main(tr, capsys, monkeypatch):

    args = (
        '--pager', '',
        '--rename', 'return o + o',
    )
    origs = ('a', 'b', 'c')
    file_sys = origs
    exp_file_sys = ('aa', 'bb', 'cc')

    monkeypatch.setattr('sys.stdin', io.StringIO('yes'))
    plan = main(args + origs, file_sys = file_sys)
    assert tuple(plan.file_sys) == exp_file_sys
    cap = capsys.readouterr()
    assert cap.err == ''
    # TODO: adjust this to something sane.
    assert cap.out == 'Paths to be renamed (total 3, listed 3).\n\na\naa\n\nb\nbb\n\nc\ncc\n\n\nRename paths (total 3, listed 3) [yes]? \nPaths renamed.\n'

