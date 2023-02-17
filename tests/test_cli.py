'''

    # TEMPLATE CODE.
    return
    wa = create_wa(origs, news)
    wa = create_wa(origs, news, rootless = True)
    outs = create_outs(wa.origs, wa.news)
    cli = CliRenamerSIO(*wa.origs, *wa.news, ...)
    cli.run()
    with wa.cd():
        cli.run()
    assert cli.err == ''
    assert cli.out == ''
    assert cli.out == outs.regular_output
    assert cli.log == ''
    assert cli.logs_valid_json is cli.OK
    wa.check()
    wa.check(no_change = True)
    assert cli.success
    assert cli.failure

'''


import json
import pytest
import re
import sys
import traceback

from io import StringIO
from pathlib import Path
from string import ascii_lowercase

from mvs.cli import main, CliRenamer, CLI
from mvs.problems import CONTROLS, PROBLEM_FORMATS as PF
from mvs.utils import write_to_clipboard, CON, MSG_FORMATS as MF
from mvs.version import __version__

####
# Helper class to test CliRenamer instances.
####

class CliRenamerSIO(CliRenamer):
    # A thin wrapper around a CliRenamer:
    #
    # - Adds args to disable pagination by default.
    # - Includes --yes among args by default.
    # - Sets I/O handles to be StringIO instances, so we can capture outputs.
    # - Adds a convenience (replies) to feed stdin.
    # - Adds various properties/etc to simplify assertion making.

    OK = 'LOGS_OK'

    def __init__(self, *args, pager = '', yes = True, replies = ''):
        args = (
            args +
            ('--pager', pager) +
            (('--yes',) if yes else ())
        )
        super().__init__(
            args,
            stdout = StringIO(),
            stderr = StringIO(),
            stdin = StringIO(replies),
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

    @property
    def log_plan(self):
        return parse_log(self.log, self.LOG_TYPE.plan)

    @property
    def log_tracking(self):
        return parse_log(self.log, self.LOG_TYPE.tracking)

    @property
    def log_plan_dict(self):
        return json.loads(self.log_plan)

    @property
    def log_tracking_dict(self):
        return json.loads(self.log_tracking)

    @property
    def logs_valid_json(self):
        plan = self.log_plan
        tracking = self.log_tracking
        try:
            json.loads(plan)
            json.loads(tracking)
            return self.OK
        except Exception as e:
            return dict(
                plan = plan,
                tracking = tracking,
                trackback = traceback.format_exc(),
            )

####
# Helper functions.
####

def can_use_clipboard():
    # I could not get pyperclip working on ubuntu in Github Actions,
    # I'm using this to bypass clipboard checks.
    return sys.platform != 'linux'

def parse_log(text, log_type):
    # CliRenamerSIO collects logging output from CliRenamer
    # in a single StringIO, which means that the plan-log and
    # the tracking-log are combined. This function takes a
    # log_type and returns the desired portion of the log output.

    # Find the index of the divider between the two logging calls.
    # If we don't find it, all content will go to the plan-log.
    div = '\n}{\n'
    try:
        i = text.index(div) + 2
    except ValueError:
        i = len(text)

    # Partition the text into the two logs and return the requested one.
    logs = {
        CliRenamer.LOG_TYPE.plan:     text[0 : i],
        CliRenamer.LOG_TYPE.tracking: text[i : None],
    }
    return logs[log_type]

####
# Command-line arguments and options.
####

def test_version_and_help(tr):
    # Exercise the command-line options that report
    # information about the app and exit immediately.

    # A helper.
    def do_checks(*args):
        cli = CliRenamerSIO('mvs', *args)
        cli.run()
        assert cli.success
        assert cli.err == ''
        assert cli.log == ''
        return cli

    # Version.
    cli = do_checks('--version')
    assert cli.out == MF.cli_version_msg + CON.newline

    # Details.
    cli = do_checks('--details')
    assert cli.out.split() == CLI.post_epilog.split()

    # Help.
    cli = do_checks('--version', '--help')
    assert cli.out.startswith(f'Usage: {CON.app_name}')
    assert len(cli.out) > 2000
    assert CLI.description[:40] in cli.out
    for opt in ('--clipboard', '--paragraphs', '--rename'):
        assert f'\n  {opt}' in cli.out
    for oc in CLI.opts_config:
        assert oc['help'][0:40] in cli.out

def test_indent_and_posint(tr, create_wa, create_outs):
    # Paths and args.
    origs = ('a', 'b', 'c')
    news = ('aa', 'bb', 'cc')
    args = ('--rename', 'return o + o', '--indent')
    valid_indents = ('2', '4', '8')
    invalid_indents = ('-4', 'xx', '0', '1.2')

    # Valid indent values.
    for i in valid_indents:
        wa = create_wa(origs, news, rootless = True)
        outs = create_outs(wa.origs, wa.news)
        cli = CliRenamerSIO(*args, i, *wa.origs)
        with wa.cd():
            cli.run()
        wa.check()
        assert cli.success
        assert cli.err == ''
        assert cli.out == outs.regular_output
        assert cli.logs_valid_json is cli.OK

    # Invalid indent values.
    for i in invalid_indents:
        wa = create_wa(origs, news, rootless = True)
        cli = CliRenamerSIO(*args, i, *wa.origs)
        with wa.cd():
            cli.run()
        wa.check(no_change = True)
        assert cli.failure
        assert cli.out == ''
        assert cli.log == ''
        exp = '--indent: invalid positive_int value'
        assert exp in cli.err
        assert cli.err.startswith(f'Usage: {CON.app_name}')

####
# Basic renaming usage.
####

def test_basic_use_cases(tr, create_wa, create_outs):
    # Paths.
    origs = ('a', 'b', 'c')
    news = ('aa', 'bb', 'cc')

    # Helper.
    def do_checks(*xs, include_news = True):
        wa = create_wa(origs, news)
        outs = create_outs(wa.origs, wa.news)
        args = wa.origs + (wa.news if include_news else ()) + xs
        cli = CliRenamerSIO(*args)
        cli.run()
        assert cli.success
        assert cli.out == outs.regular_output
        assert cli.err == ''
        assert cli.logs_valid_json is cli.OK
        wa.check()

    # Basic use cases:
    # - Flat structure as the default.
    # - Flat passed explicitly.
    # - Renaming via code.
    do_checks()
    do_checks('--flat')
    do_checks(
        '--rename',
        'return p.with_name(p.name + p.name)',
        include_news = False,
    )

####
# Input paths and sources.
####

def test_no_input_paths(tr, create_wa, create_outs):
    origs = ('a', 'b', 'c')
    news = ('aa', 'bb', 'cc')
    empty_paths = ('', '   ', ' ')

    # Initial scenario: it works.
    wa = create_wa(origs, news)
    outs = create_outs(wa.origs, wa.news)
    cli = CliRenamerSIO(
        *wa.origs,
        *wa.news,
    )
    cli.run()
    assert cli.err == ''
    assert cli.out == outs.regular_output
    assert cli.logs_valid_json is cli.OK
    assert cli.success
    wa.check()

    # But it fails if we omit the input paths.
    wa = create_wa(origs, news)
    cli = CliRenamerSIO()
    cli.run()
    assert cli.err.startswith(MF.opts_require_one)
    assert cli.out == ''
    assert cli.log == ''
    assert cli.failure
    for name in CLI.sources.keys():
        assert name in cli.err
    wa.check(no_change = True)

    # It also fails if the input paths are empty.
    wa = create_wa(origs, news)
    cli = CliRenamerSIO(*empty_paths)
    cli.run()
    assert PF.parsing_no_paths in cli.err
    assert cli.out == ''
    assert cli.log == ''
    assert cli.failure

def test_odd_number_inputs(tr, create_wa, create_outs):
    # An odd number of inputs will fail.
    origs = ('z1', 'z2', 'z3')
    news = ()
    wa = create_wa(origs, news)
    cli = CliRenamerSIO(*wa.origs, *wa.news)
    cli.run()
    got = cli.err
    exp1 = MF.prepare_failed_cli.split(CON.colon)[0]
    exp2 = PF.parsing_imbalance
    assert got.startswith(exp1)
    assert exp2 in got
    assert cli.out == ''
    assert cli.log == ''
    assert cli.failure
    wa.check(no_change = True)

def test_sources(tr, create_wa, create_outs):
    # Paths and args.
    origs = ('z1', 'z2', 'z3')
    news = ('A1', 'A2', 'A3')
    extras = ('input_paths.txt',)

    # Helper to assemble path inputs into a chunk of text.
    def args_text(wa):
        return CON.newline.join(wa.origs + wa.news)

    # Helper for checks during successful renamings.
    def do_checks(wa, *xs, **kws):
        outs = create_outs(wa.origs, wa.news)
        cli = CliRenamerSIO(*xs, **kws)
        cli.run()
        assert cli.out == outs.regular_output
        assert cli.err == ''
        assert cli.logs_valid_json is cli.OK
        wa.check()
        assert cli.success

    # Base scenario: paths via args.
    wa = create_wa(origs, news)
    do_checks(wa, *wa.origs, *wa.news)

    # Paths via stdin.
    wa = create_wa(origs, news)
    do_checks(wa, '--stdin', replies = args_text(wa))

    # Paths via clipboard.
    if can_use_clipboard():
        wa = create_wa(origs, news)
        write_to_clipboard(args_text(wa))
        do_checks(wa, '--clipboard')

    # Paths via a file.
    wa = create_wa(origs, news, extras)
    inputs_path = wa.extras[0]
    with open(inputs_path, 'w') as fh:
        fh.write(args_text(wa))
    do_checks(wa, '--file', inputs_path)

    # Too many sources.
    wa = create_wa(origs, news)
    cli = CliRenamerSIO('--clipboard', '--stdin')
    cli.run()
    got = cli.err
    assert got.startswith(MF.opts_mutex)
    assert '--clipboard' in got
    assert '--stdin' in got
    assert cli.out == ''
    assert cli.log == ''
    wa.check(no_change = True)
    assert cli.failure

####
# Dryrun and no-confirmation.
####

@pytest.mark.skip(reason = 'drop-fake-fs')
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

@pytest.mark.skip(reason = 'drop-fake-fs')
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

@pytest.mark.skip(reason = 'drop-fake-fs')
def test_rename_paths_raises(tr):
    # Paths and args.
    origs = ('z1', 'z2', 'z3')
    news = ('ZZ1', 'ZZ2', 'ZZ3')
    args = origs + news + ('--yes',)

    # A working scenario.
    cli = CliRenamerSIO(*args, file_sys = origs)
    cli.run()
    assert cli.success
    cli.check_file_sys(*news)

    # Same scenario, but using do_prepare() and do_rename().
    cli = CliRenamerSIO(*args, file_sys = origs)
    cli.do_prepare()
    cli.do_rename()
    assert cli.success
    cli.check_file_sys(*news)

    # Same scenario. Calling the methods multiple times has no adverse effect.
    cli = CliRenamerSIO(*args, file_sys = origs)
    cli.do_prepare()
    cli.do_prepare()
    cli.do_rename()
    assert cli.plan.tracking_rp is None
    cli.do_rename()
    assert cli.success
    cli.check_file_sys(*news)
    assert cli.plan.tracking_rp is None

    # Helper to format expected error text for subsequent checks.
    def exp_err_text(tracking_index):
        msg = MF.renaming_raised.format(tracking_index)
        return msg.strip().split(CON.colon)[0]

    # Same scenario, but we will set plan.has_renamed to trigger
    # an exception when plan.rename_paths() is called.
    cli = CliRenamerSIO(*args, file_sys = origs)
    cli.do_prepare()
    cli.plan.has_renamed = True
    cli.do_rename()
    assert cli.failure
    exp = exp_err_text(cli.plan.TRACKING.not_started)
    assert cli.err.strip().startswith(exp)
    assert 'raise MvsError(MF.rename_done_already)' in cli.err

    # Same scenario, but this time we will trigger the exception via
    # the raise_at attribute, so we can check the tracking_index in
    # the tracking log and in the command-line error message.
    n = 1
    cli = CliRenamerSIO(*args, file_sys = origs)
    cli.do_prepare()
    assert cli.plan.tracking_rp is None
    cli.plan.raise_at = n
    cli.do_rename()
    assert cli.failure
    got = json.loads(cli.log(cli.LOG_TYPE.tracking))
    assert got == dict(tracking_index = n)
    assert cli.plan.tracking_rp.orig == 'z2'
    exp = exp_err_text(n)
    assert cli.err.strip().startswith(exp)
    assert 'ZeroDivisionError: SIMULATED_ERROR' in cli.err

@pytest.mark.skip(reason = 'drop-fake-fs')
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
    assert cli.log() == ''
    assert cli.err.startswith(exp_cli_prep)
    assert PF.all_filtered in cli.err

####
# Textual outputs.
####

@pytest.mark.skip(reason = 'drop-fake-fs')
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
    got = json.loads(cli.log(cli.LOG_TYPE.plan))
    assert got['version'] == __version__
    ks = ['current_directory', 'opts', 'inputs', 'rename_pairs', 'problems']
    for k in ks:
        assert k in got

    # Also check the tracking log.
    got = json.loads(cli.log(cli.LOG_TYPE.tracking))
    assert tuple(got) == ('tracking_index',)

@pytest.mark.skip(reason = 'drop-fake-fs')
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
    log_plan = parse_log(fhs['logfh'], CliRenamer.LOG_TYPE.plan)
    log_tracking = parse_log(fhs['logfh'], CliRenamer.LOG_TYPE.tracking)
    d = json.loads(log_plan)
    assert 'version' in d
    assert 'opts' in d
    d = json.loads(log_tracking)
    assert 'tracking_index' in d

@pytest.mark.skip(reason = 'drop-fake-fs')
def test_e2e_basic_rename(tr):
    # End to end: basic renaming scenario.
    origs = ('a', 'b')
    news = ('c', 'd')
    origs, news = tr.temp_area(origs, news)
    ex, fhs = execute_main(*origs, *news)
    assert ex.args[0] == CON.exit_ok
    check_main_paths(origs, news)
    check_main_outputs(fhs)

@pytest.mark.skip(reason = 'drop-fake-fs')
def test_e2e_create_parent(tr):
    # End to end: renaming that requires parent creation.
    origs = ('a', 'b')
    news = ('foo/c', 'foo/d')
    origs, news = tr.temp_area(origs, news)
    ex, fhs = execute_main(*origs, *news, '--create', 'parent')
    check_main_paths(origs, news)
    check_main_outputs(fhs)

@pytest.mark.skip(reason = 'drop-fake-fs')
def test_e2e_clobber(tr):
    # End to end: renaming that clobbers existing paths.
    origs = ('a', 'b')
    news = ('c', 'd')
    extras = ('c', 'x')
    origs, news, extras = tr.temp_area(origs, news, extras)
    ex, fhs = execute_main(*origs, *news, '--clobber', 'existing')
    check_main_outputs(fhs)
    check_main_paths(origs, news + extras)

####
# Problem control.
####

@pytest.mark.skip(reason = 'drop-fake-fs')
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
    assert cli.log() == ''
    assert cli.err.startswith(exp_conflict)
    assert CONTROLS.skip in cli.err
    assert CONTROLS.clobber in cli.err

####
# Miscellaneous.
####

@pytest.mark.skip(reason = 'drop-fake-fs')
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
        MF.prefs_reading_failed,
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
        assert cli.log() == ''
        exp = fmt.split('{')[0]
        assert exp in cli.err

