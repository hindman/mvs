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
        print()             # main() twice
        subprocess          # paginate(), which also uses print()
        input()             # get_confirmation()

    Exiting:
        - Catch SystemExit.

        sys.exit()          # halt()

    Getting user input:

        sys.stdin.read()    # collect_input_paths()
        input()             # get_confirmation()

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


def main(args = None):
    args = sys.argv[1:] if args is None else args
    cli = CliRenamer(args)
    code = cli.go()
    sys.exit(code)

class CliRenamerIO(CliRenamer):

    def __init__(self, args, file_sys = None, replies = tuple()):
        reply_txt = CON.newline.join(replies)
        super().__init__(
           *args,
            file_sys = file_sys,
            stdout = StringIO(),
            stderr = StringIO(),
            stdin = StringIO(reply_txt),
            logfh = StringIO(),
        )

    @property
    def success(self):
        return self.exit_code = CON.exit_ok

    @property
    def out(self):
        return self.stdout.getvalue()

    @property
    def err(self):
        return self.stderr.getvalue()

    @property
    def log(self):
        return self.logfh.getvalue()

def test_version_and_help(tr, capsys):
    # Version.
    cli = cli_renamer_io('bmv', '--version')
    cli.go()
    assert cli.success
    assert cli.out = f'{CON.app_name} v{__version__}\n'
    assert cli.err = ''

class CliRenamer:

    def __init__(self,
                 args,
                 file_sys = None,
                 stdout = sys.stdout,
                 stderr = sys.stderr,
                 stdin = sys.stdin,
                 logfh = None)
        self.args = args
        ...

        self.opts = None
        self.inputs = None
        self.plan = None

    def go(self):

        # Parse args.
        self.opts = self.parse_command_line_args()
        if self.done:
            return self.exit_code

        # Collect the input paths.
        try:
            self.inputs = self.collect_input_paths()
        except Exception as e:
            ...
            return self.exit_code

        # Initialize RenamingPlan.
        opts = self.opts
        self.plan = RenamingPlan(
            inputs = self.inputs,
            rename_code = opts.rename,
            structure = self.get_structure(),
            seq_start = opts.seq,
            seq_step = opts.step,
            filter_code = opts.filter,
            indent = opts.indent,
            file_sys = self.file_sys,
            **fail_controls_kws(opts),
        )

        # Prepare the RenamingPlan and halt if it failed.
        plan.prepare()
        if plan.failed:
            msg = FAIL.prepare_failed_cli.format(plan.first_failure.msg)
            self.stderr.write(msg)
            return CON.exit_fail

        # Print the renaming listing.
        listing = listing_msg(plan.rps, opts.limit, 'Paths to be renamed{}.\n')
        self.paginate(listing)

        # Stop if dryrun mode.
        if opts.dryrun:
            self.stdout.write(CON.no_action_msg)
            return CON.exit_ok

        # User confirmation.
        if not opts.yes:
            msg = tallies_msg(plan.rps, opts.limit, '\nRename paths{}')
            if get_confirmation(msg, expected = 'yes'):
                print(CON.paths_renamed_msg)
            else:
                halt(CON.exit_ok, CON.no_action_msg)

        # Log the renamings.
        if not opts.nolog:
            log_data = collect_logging_data(opts, plan)
            write_to_json_file(log_file_path(), log_data)

        # Rename.
        try:
            plan.rename_paths()
            return CON.exit_ok if file_sys is None else plan
        except Exception as e:
            tb = traceback.format_exc()
            msg = FAIL.renaming_raised.format(tb)
            halt(CON.exit_fail, msg)




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

