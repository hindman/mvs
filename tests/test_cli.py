import json
import pytest
import re
import sys
import traceback

from io import StringIO
from pathlib import Path
from string import ascii_lowercase
from types import SimpleNamespace

from mvs.cli import main, CliRenamer, CLI
from mvs.plan import RenamingPlan
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
    # - Adds a convenience to feed stdin (replies).
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

def test_dryrun(tr, create_wa, create_outs):
    # In dryrun mode, we get the expected listing, but no renaming occurs.
    origs = ('a', 'b', 'c')
    news = ('aa', 'bb', 'cc')
    wa = create_wa(origs, news, rootless = True)
    outs = create_outs(wa.origs, wa.news)
    cli = CliRenamerSIO(
        *wa.origs,
        '--rename',
        'return o + o',
        '--dryrun',
    )
    with wa.cd():
        cli.run()
    wa.check(no_change = True)
    assert cli.err == ''
    assert cli.log == ''
    assert cli.out == outs.no_action_output
    assert cli.success

def test_no_confirmation(tr, create_wa, create_outs):
    # If use does not confirm, we get the usual listing,
    # but no renaming occurs.
    origs = ('a', 'b', 'c')
    news = ('aa', 'bb', 'cc')
    wa = create_wa(origs, news, rootless = True)
    outs = create_outs(wa.origs, wa.news)
    cli = CliRenamerSIO(
        *wa.origs,
        '--rename',
        'return o + o',
        yes = False,
    )
    with wa.cd():
        cli.run()
    wa.check(no_change = True)
    assert cli.err == ''
    assert cli.log == ''
    assert cli.out == outs.no_confirm_output
    assert cli.success

####
# User-supplied code.
####

def test_rename_paths_raises(tr, create_wa, create_outs):
    # Paths, etc.
    origs = ('z1', 'z2', 'z3')
    news = ('ZZ1', 'ZZ2', 'ZZ3')
    expecteds = news[:1] + origs[1:]
    NSTART = RenamingPlan.TRACKING.not_started

    def do_checks(mode):
        wa = create_wa(origs, news)
        outs = create_outs(wa.origs, wa.news)
        cli = CliRenamerSIO(*wa.origs, *wa.news)
        if mode == 'run':
            cli.run()
        elif mode == 'do':
            cli.do_prepare()
            cli.do_rename()
        elif mode == 'multiple-do':
            cli.do_prepare()
            cli.do_prepare()
            assert cli.plan.tracking_rp is None
            cli.do_rename()
            assert cli.plan.tracking_rp is None
            cli.do_rename()
            assert cli.plan.tracking_rp is None
        else:
            assert False
        wa.check()
        assert cli.err == ''
        assert cli.out == outs.regular_output
        assert cli.logs_valid_json is cli.OK
        assert cli.success

    # A working scenario.
    do_checks('run')

    # Same scenario, but using do_prepare() and do_rename(),
    # either once or even multiple times.
    do_checks('do')
    do_checks('multiple-do')

    # Helper to format expected error text for subsequent checks.
    def exp_err_text(tracking_index):
        msg = MF.renaming_raised.format(tracking_index)
        return msg.strip().split(CON.colon)[0]

    # Same scenario, but we will set plan.has_renamed to trigger
    # an exception when plan.rename_paths() is called.
    wa = create_wa(origs, news)
    outs = create_outs(wa.origs, wa.news)
    cli = CliRenamerSIO(*wa.origs, *wa.news)
    cli.do_prepare()
    cli.plan.has_renamed = True
    cli.do_rename()
    wa.check(no_change = True)
    assert cli.plan.tracking_index == NSTART
    got = cli.err
    exp = exp_err_text(NSTART)
    assert got.strip().startswith(exp)
    assert 'raise MvsError(MF.rename_done_already)' in got
    assert cli.failure
    assert cli.out.rstrip() == outs.paths_to_be_renamed.rstrip()
    assert cli.logs_valid_json is cli.OK

    # Same scenario, but this time we will trigger the exception via
    # the raise_at attribute, so we can check the tracking_index in
    # the tracking log and in the command-line error message.
    N = 1
    wa = create_wa(origs, news, (), expecteds)
    outs = create_outs(wa.origs, wa.news)
    cli = CliRenamerSIO(*wa.origs, *wa.news)
    cli.do_prepare()
    assert cli.plan.tracking_rp is None
    assert cli.plan.tracking_index == NSTART
    cli.plan.raise_at = N
    cli.do_rename()
    wa.check()
    assert cli.plan.tracking_rp.orig == wa.origs[N]
    assert cli.plan.tracking_index == N
    assert cli.logs_valid_json is cli.OK
    assert cli.log_tracking_dict == dict(tracking_index = N)
    assert cli.out.rstrip() == outs.paths_to_be_renamed.rstrip()
    got = cli.err
    exp = exp_err_text(N)
    assert got.strip().startswith(exp)
    assert 'ZeroDivisionError: SIMULATED_ERROR' in got
    assert cli.failure

def test_filter_all(tr, create_wa, create_outs):
    origs = ('a', 'b', 'c')
    news = ('aa', 'bb', 'cc')
    exp_cli_prep = MF.prepare_failed_cli.split(':')[0]
    exp_conflict = MF.conflicting_controls.split(':')[0]

    # Initial scenario: it works.
    wa = create_wa(origs, news)
    outs = create_outs(wa.origs, wa.news)
    cli = CliRenamerSIO(*wa.origs, *wa.news)
    cli.run()
    assert cli.err == ''
    assert cli.out == outs.regular_output
    assert cli.logs_valid_json is cli.OK
    wa.check()
    assert cli.success

    # But it fails if the user's code filters everything out.
    wa = create_wa(origs, news)
    outs = create_outs(wa.origs, wa.news)
    cli = CliRenamerSIO(
        *wa.origs,
        *wa.news,
        '--filter',
        'return False',
    )
    cli.run()
    assert cli.err.startswith(exp_cli_prep)
    assert PF.all_filtered in cli.err
    assert cli.out == ''
    assert cli.log == ''
    assert cli.failure
    wa.check(no_change = True)

####
# Textual outputs.
####

def test_log(tr, create_wa, create_outs):
    # Paths and args.
    origs = ('a', 'b', 'c')
    news = ('aa', 'bb', 'cc')

    # A basic renaming scenario.
    # We can load its log file and check that it is a dict
    # with some of the expected keys.
    wa = create_wa(origs, news)
    outs = create_outs(wa.origs, wa.news)
    cli = CliRenamerSIO(*wa.origs, *wa.news)
    cli.run()
    assert cli.err == ''
    assert cli.out == outs.regular_output
    assert cli.logs_valid_json is cli.OK
    wa.check()
    assert cli.success
    got = cli.log_plan_dict
    assert got['version'] == __version__
    ks = ['current_directory', 'opts', 'inputs', 'rename_pairs', 'problems']
    for k in ks:
        assert k in got
    got = cli.log_tracking_dict
    assert got == dict(tracking_index = cli.plan.TRACKING.done)

def test_pagination(tr, create_wa, create_outs):
    # Paths.
    origs = tuple(ascii_lowercase)
    news = tuple(o + o for o in origs)

    # Exercise the paginate() function by using cat and /dev/null.
    wa = create_wa(origs, news)
    outs = create_outs(wa.origs, wa.news)
    cli = CliRenamerSIO(
        *wa.origs,
        *wa.news,
        pager = 'cat > /dev/null',
    )
    cli.run()
    wa.check()
    assert cli.err == ''
    assert cli.logs_valid_json is cli.OK
    assert cli.out.lstrip() == outs.paths_renamed.lstrip()
    assert cli.success

####
# Exercising main().
####

def test_main(tr, create_wa, create_outs):
    # Paths.
    origs = ('xx', 'yy')
    news = ('xx.new', 'yy.new')

    # Helper to check that logging output is valid JSON.
    def check_log(cli, log_name):
        log_type = getattr(CliRenamer.LOG_TYPE, log_name)
        text = parse_log(cli.logfh, log_type)
        d = json.loads(text)
        assert isinstance(d, dict)

    # File handles to pass into main().
    fhs = dict(
        stdout = StringIO(),
        stderr = StringIO(),
        stdin = StringIO(),
        logfh = StringIO(),
    )

    # Create work area.
    wa = create_wa(origs, news)
    outs = create_outs(wa.origs, wa.news)

    # Call main(). It should exit successfully.
    args = wa.origs + wa.news + ('--yes', '--pager', '')
    with pytest.raises(SystemExit) as einfo:
        main(args, **fhs)
    einfo.value.code == CON.exit_ok

    # Confirm that paths were renamed as expected.
    wa.check()

    # Check textual outputs.
    cli = SimpleNamespace(**{
        k : fh.getvalue()
        for k, fh in fhs.items()
    })
    assert cli.stdout == outs.regular_output
    assert cli.stderr == ''
    assert cli.stdin == ''
    check_log(cli, 'plan')
    check_log(cli, 'tracking')

####
# Problem control.
####

def test_some_failed_rps(tr, create_wa, create_outs):
    # Paths, options, expectations.
    origs = ('z1', 'z2', 'z3', 'z4')
    news = ('A1', 'A2', 'A3', 'A4')
    extras = ('A1', 'A2')
    expecteds = ('z1', 'z2', 'A3', 'A4') + extras
    opt_skip = ('--skip', 'existing')
    opt_clobber = ('--clobber', 'existing')
    exp_cli_prep = MF.prepare_failed_cli.split(':')[0]
    exp_conflict = MF.conflicting_controls.split('{')[0]

    # Initial scenario fails: 2 of the new paths already exist.
    # No renaming occurs.
    wa = create_wa(origs, news, extras)
    outs = create_outs(wa.origs, wa.news)
    cli = CliRenamerSIO(*wa.origs, *wa.news)
    cli.run()
    wa.check(no_change = True)
    assert cli.err.startswith(exp_cli_prep)
    assert PF.existing in cli.err
    assert cli.out == ''
    assert cli.log == ''
    assert cli.failure

    # Renaming succeeds if we use --skip.
    wa = create_wa(origs, news, extras, expecteds)
    outs = create_outs(wa.origs[2:], wa.news[2:])
    cli = CliRenamerSIO(
        *wa.origs,
        *wa.news,
        *opt_skip,
    )
    cli.run()
    wa.check()
    assert cli.out == outs.regular_output
    assert cli.logs_valid_json is cli.OK
    assert cli.err == ''
    assert cli.success

    # Renaming fails if we pass both failure-control options.
    wa = create_wa(origs, news, extras)
    cli = CliRenamerSIO(
        *wa.origs,
        *wa.news,
        *opt_skip,
        *opt_clobber,
    )
    cli.run()
    wa.check(no_change = True)
    got = cli.err
    assert got.startswith(exp_conflict)
    assert CONTROLS.skip in got
    assert CONTROLS.clobber in got
    assert cli.out == ''
    assert cli.log == ''
    assert cli.failure

####
# Miscellaneous.
####

def test_wrapup_with_tb(tr, create_wa):
    # Excercises all calls of wrapup_with_tb() and checks for expected
    # attribute changes. Those code branches are a hassle to reach during
    # testing, are unlikely to occur in real usage, and do nothing interesting
    # other than call the method tested here. So they are pragma-ignored by
    # test-coverage. Here we simple exercise the machinery to insure against MF
    # attribute names becoming outdated.
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
        wa = create_wa(origs, news)
        cli = CliRenamerSIO(*wa.origs, *wa.news)
        assert cli.exit_code is None
        assert cli.done is False
        cli.wrapup_with_tb(fmt)
        assert cli.exit_code == CON.exit_fail
        assert cli.done is True
        assert cli.out == ''
        assert cli.log == ''
        got = cli.err
        exp = fmt.split('{')[0]
        assert exp in got
        wa.check(no_change = True)

