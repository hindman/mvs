import json
import pytest
import re

from io import StringIO
from pathlib import Path
from string import ascii_lowercase

from bmv.cli import main, CliRenamer, CLI
from bmv.problems import CONTROLS, PROBLEM_FORMATS as PF
from bmv.utils import write_to_clipboard, CON, MSG_FORMATS as MF
from bmv.version import __version__

####
# Helper class to test CliRenamer instances.
####

class CliRenamerSIO(CliRenamer):
    # A thin wrapper around a CliRenamer:
    #
    # - Adds args to disable pagination by default.
    # - Sets I/O handles to be StringIO instances, so we can capture outputs.
    # - Adds a convenience (yes) to simulate user confirmation.
    # - Adds a convenience (replies) to feed stdin.
    # - Adds a few properties/methods to simplify assertion making.

    def __init__(self,
                 *args,
                 file_sys = None,
                 replies = '',
                 yes = False,
                 pager = ''):
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

####
# Command-line arguments and options.
####

def test_version_and_help(tr):
    # Version.
    cli = CliRenamerSIO('bmv', '--version')
    cli.run()
    assert cli.success
    assert cli.err == ''
    assert cli.out == MF.cli_version_msg + CON.newline

    # Help.
    cli = CliRenamerSIO('bmv', '--version', '--help')
    cli.run()
    assert cli.success
    assert cli.err == ''
    assert cli.out.startswith(f'Usage: {CON.app_name}')
    assert len(cli.out) > 3000
    for opt in ('--clipboard', '--paragraphs', '--rename'):
        assert f'\n  {opt}' in cli.out
    for oc in CLI.opts_config:
        assert oc['help'][0:40] in cli.out

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
        assert cli.err.startswith(f'Usage: {CON.app_name}')

####
# Basic renaming usage.
####

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

####
# Input paths and sources.
####

def test_no_input_paths(tr):
    origs = ('a', 'b', 'c')
    news = ('aa', 'bb', 'cc')
    rename_args = ('--rename', 'return o + o')
    empty_paths = ('', '   ', ' ')

    # Initial scenario: it works.
    cli = CliRenamerSIO(
        *rename_args,
        *origs,
        file_sys = origs,
        yes = True,
    )
    cli.run()
    assert cli.success
    cli.check_file_sys(*news)

    # But it fails if we omit the input paths.
    cli = CliRenamerSIO(
        *rename_args,
        file_sys = origs,
        yes = True,
    )
    cli.run()
    assert cli.failure
    assert cli.out == ''
    assert cli.log == ''
    assert cli.err.startswith(MF.opts_require_one)
    for name in CLI.sources.keys():
        assert name in cli.err

    # It also fails if the input paths are empty.
    cli = CliRenamerSIO(
        *rename_args,
        *empty_paths,
        file_sys = origs,
        yes = True,
    )
    cli.run()
    assert cli.failure
    assert cli.out == ''
    assert cli.log == ''
    assert PF.parsing_no_paths in cli.err

def test_odd_number_inputs(tr):
    # An odd number of inputs.
    origs = ('z1',)
    cli = CliRenamerSIO(*origs, file_sys = origs)
    cli.run()
    assert cli.failure
    assert cli.out == ''
    got = cli.err
    exp1 = MF.prepare_failed_cli.split(CON.colon)[0]
    exp2 = PF.parsing_imbalance
    assert got.startswith(exp1)
    assert exp2 in got

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

    # Too many sources.
    cli = CliRenamerSIO('--clipboard', '--stdin', yes, file_sys = origs)
    cli.run()
    assert cli.failure
    assert cli.err.startswith(MF.opts_mutex)
    assert '--clipboard' in cli.err
    assert '--stdin' in cli.err

####
# Dryrun and no-confirmation.
####

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

####
# User-supplied code.
####

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

    # Same thing. Calling the methods multiple times has no adverse effect.
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
    exp = MF.renaming_raised.strip().split(CON.colon)[0]
    assert cli.err.strip().startswith(exp)
    assert 'raise BmvError(MF.rename_done_already)' in cli.err

def test_filter_all(tr):
    origs = ('a', 'b', 'c')
    news = ('aa', 'bb', 'cc')
    args = origs + news
    exp_cli_prep = MF.prepare_failed_cli.split(':')[0]
    exp_conflict = MF.conflicting_controls.split(':')[0]

    # Initial scenario: it works.
    cli = CliRenamerSIO(
        *args,
        file_sys = origs,
        yes = True,
    )
    cli.run()
    assert cli.success
    cli.check_file_sys(*news)

    # But it fails if the user's code filters everything out.
    cli = CliRenamerSIO(
        *args,
        '--filter',
        'return False',
        file_sys = origs,
        yes = True,
    )
    cli.run()
    assert cli.failure
    assert cli.out == ''
    assert cli.log == ''
    assert cli.err.startswith(exp_cli_prep)
    assert PF.all_filtered in cli.err

####
# Textual outputs.
####

def test_log(tr):
    # Paths and args.
    origs = ('a', 'b', 'c')
    news = ('aa', 'bb', 'cc')
    rename_args = ('--rename', 'return o + o')

    # A basic scenario that works.
    cli = CliRenamerSIO(*rename_args, *origs, file_sys = origs, yes = True)
    cli.run()
    assert cli.success
    cli.check_file_sys(*news)

    # We can load its log file and check that it is a dict
    # with some of the expected keys.
    got = json.loads(cli.log)
    assert got['version'] == __version__
    ks = ['current_directory', 'opts', 'inputs', 'rename_pairs', 'problems']
    for k in ks:
        assert k in got

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

####
# End to end tests: real file system operations via main().
####

def execute_main(*args):
    # Helper to execute main() and return program textual outputs.
    fhs = dict(
        stdout = StringIO(),
        stderr = StringIO(),
        stdin = StringIO(),
        logfh = StringIO(),
    )
    args = args + ('--yes', '--pager', '')
    with pytest.raises(SystemExit) as einfo:
        main(args, **fhs)
    fhs = {
        k : fh.getvalue()
        for k, fh in fhs.items()
    }
    return (einfo.value, fhs)

def check_main_paths(origs, news):
    # Helper to check the resulting file system after renaming.
    checks = (
        (origs, False),
        (news, True),
    )
    for paths, exp in checks:
        for p in paths:
            if p.endswith('/'):
                assert (p, Path(p).is_dir()) == (p, exp)
            else:
                assert (p, Path(p).is_file()) == (p, exp)

def check_main_outputs(fhs):
    # Helper to check the textual outputs from a main() call.
    out = fhs['stdout']
    err = fhs['stderr']
    assert err == ''
    assert 'Paths renamed.' in out
    assert 'Paths to be renamed (total' in out
    d = json.loads(fhs['logfh'])
    assert 'version' in d
    assert 'opts' in d

def test_e2e_basic_rename(tr):
    # End to end: basic renaming scenario.
    origs = ('a', 'b')
    news = ('c', 'd')
    origs, news = tr.temp_area(origs, news)
    ex, fhs = execute_main(*origs, *news)
    assert ex.args[0] == CON.exit_ok
    check_main_paths(origs, news)
    check_main_outputs(fhs)

def test_e2e_create_parent(tr):
    # End to end: renaming that requires parent creation.
    origs = ('a', 'b')
    news = ('foo/c', 'foo/d')
    origs, news = tr.temp_area(origs, news)
    ex, fhs = execute_main(*origs, *news, '--create', 'parent')
    check_main_paths(origs, news)
    check_main_outputs(fhs)

def test_e2e_clobber(tr):
    # End to end: renaming that clobbers existing paths.
    origs = ('a', 'b')
    news = ('c', 'd')
    extras = ('c', 'x')
    origs, news, extras = tr.temp_area(origs, news, extras)
    ex, fhs = execute_main(*origs, *news, '--clobber', 'existing')
    check_main_paths(origs, news + extras)
    check_main_outputs(fhs)

####
# Problem control.
####

def test_some_failed_rps(tr):
    # Paths, args, file-sys, options, expectations.
    origs = ('z1', 'z2', 'z3', 'z4')
    news = ('A1', 'A2', 'A3', 'A4')
    args = origs + news
    file_sys = origs + news[1:3]
    exp_file_sys = ('z2', 'z3', 'A2', 'A3', 'A1', 'A4')
    opt_skip = ('--skip', 'existing')
    opt_clobber = ('--clobber', 'existing')
    exp_cli_prep = MF.prepare_failed_cli.split(':')[0]
    exp_conflict = MF.conflicting_controls.split('{')[0]

    # Initial scenario fails: 2 of the new paths already exist.
    cli = CliRenamerSIO(
        *args,
        file_sys = file_sys,
        yes = True,
    )
    cli.run()
    assert cli.failure
    assert cli.err.startswith(exp_cli_prep)
    assert PF.existing in cli.err

    # Renaming succeeds if we pass --skip-existing-new.
    cli = CliRenamerSIO(
        *args,
        *opt_skip,
        file_sys = file_sys,
        yes = True,
    )
    cli.run()
    assert cli.success
    cli.check_file_sys(*exp_file_sys)

    # Renaming fails if we pass both failure-control options.
    cli = CliRenamerSIO(
        *args,
        *opt_skip,
        *opt_clobber,
        file_sys = file_sys,
        yes = True,
    )
    cli.run()
    assert cli.failure
    assert cli.out == ''
    assert cli.log == ''
    assert cli.err.startswith(exp_conflict)
    assert CONTROLS.skip in cli.err
    assert CONTROLS.clobber in cli.err

####
# Miscellaneous.
####

def test_wrapup_with_tb(tr):
    # Excercises all calls of wrapup_with_tb() and checks for expected side
    # effects. Those branches are a hassle to reach during testing, are
    # unlikely to occur in real usage, and do nothing interesting other than
    # call the method tested here. So they are pragma-ignored by test-coverage.
    origs = ('z1', 'z2', 'z3')
    news = ('A1', 'A2', 'A3')
    args = origs + news
    fmts = (
        MF.renaming_raised,
        MF.log_writing_failed,
        MF.path_collection_failed,
        MF.plan_creation_failed,
    )
    for fmt in fmts:
        cli = CliRenamerSIO(*args, file_sys = origs, yes = True)
        assert cli.exit_code is None
        assert cli.done is False
        cli.wrapup_with_tb(fmt)
        assert cli.exit_code == CON.exit_fail
        assert cli.done is True
        assert cli.out == ''
        assert cli.log == ''
        exp = fmt.split('{')[0]
        assert exp in cli.err

