import json
import os
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

BYPASS = object()
LOGS_OK = 'LOGS_OK'

class CliRenamerSIO(CliRenamer):
    # A thin wrapper around a CliRenamer:
    #
    # - Adds args to disable pagination by default.
    # - Includes --yes among args by default.
    # - Sets I/O handles to be StringIO instances, so we can capture outputs.
    # - Adds a convenience to feed stdin (replies).
    # - Adds various properties/etc to simplify assertion making.

    def __init__(self, *args, pager = None, yes = True, replies = ''):
        pager = (
            ('--pager', '') if pager is None else
            () if pager is BYPASS else
            ('--pager', pager)
        )
        yes = ('--yes',) if yes else ()
        super().__init__(
            args + pager + yes,
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
            return LOGS_OK
        except Exception as e:
            return dict(
                plan = plan,
                tracking = tracking,
                trackback = traceback.format_exc(),
            )

####
# A mega-helper to perform common checks.
# Used by most tests.
####

def run_checks(
               # Fixtures.
               tr,
               creators,
               # WorkArea (and arbitrary positionals for CliRenamer).
               origs,
               news,
               *cli_xs,
               extras = None,
               expecteds = None,
               rootless = False,
               # UserPrefs.
               prefs = None,
               blob = None,
               # Outputs.
               outs_origs = None,
               outs_news = None,
               total = None,
               listed = None,
               # Functions allowing user to do things midway through.
               other_prep = None,
               early_checks = None,
               # Assertion making.
               check_wa = True,
               check_outs = True,
               done = True,
               failure = False,
               out = None,
               err = None,
               err_starts = None,
               err_in = None,
               log = None,
               no_change = False,
               # CliRenamer.
               cli_cls = CliRenamerSIO,
               include_origs = True,
               include_news = True,
               prepare_only = False,
               setup_only = False,
               no_checks = False,
               rename_via_do = False,
               skip_rename = False,
               **cli_kws):

    # Get the fixtures.
    create_wa, create_outs, create_prefs = creators

    # Set up preferences.
    if blob is not None:
        create_prefs(blob = blob)
    elif prefs is not None:
        create_prefs(**prefs)

    # Set up WorkArea.
    wa = create_wa(
        origs,
        news,
        extras = extras,
        expecteds = expecteds,
        rootless = rootless
    )

    # Set up Outputs.
    outs = create_outs(
        outs_origs or wa.origs,
        outs_news or wa.news,
        total = total,
        listed = listed,
    )

    # Set up CliRenamer
    args = (
        (wa.origs if include_origs else ()) +
        (wa.news if include_news else ()) +
        cli_xs
    )
    cli = cli_cls(*args, **cli_kws)

    # Return early if user does not want to do anything
    # other than create WorkArea, Outputs, and CliRenamer.
    if setup_only:
        return (wa, outs, cli)

    # Let caller do other set up stuff before renaming.
    if other_prep:
        other_prep(wa, outs, cli)

    # Run the renaming or just the preparations.
    if prepare_only:
        no_change = True
        cli.do_prepare()
    elif rename_via_do:
        cli.do_prepare()
        cli.do_rename()
    elif rootless:
        with wa.cd():
            cli.run()
    elif not skip_rename:
        cli.run()

    # Return early if user does not want to check anything.
    if no_checks:
        return (wa, outs, cli)

    # Let caller make early assertions.
    if early_checks:
        early_checks(wa, outs, cli)

    # Check work area.
    if check_wa:
        wa.check(no_change = no_change)

    # Check CliRenamer outputs.
    if check_outs:
        # Standard output.
        if callable(out):
            assert cli.out == out(wa, outs, cli)
        elif out is None:
            exp = '' if failure else outs.regular_output
            assert cli.out == exp
        elif out is not BYPASS:
            assert cli.out == out

        # Error output.
        if err_starts:
            for exp in to_tup(err_starts):
                assert cli.err.startswith(exp)
        if err_in:
            for exp in to_tup(err_in):
                assert exp in cli.err
        if err is not None:
            assert cli.err == err

        # Log output.
        if log is LOGS_OK:
            assert cli.logs_valid_json is LOGS_OK
        elif log is BYPASS:
            pass
        elif log is None and failure:
            assert cli.log == ''
        elif log is None:
            assert cli.logs_valid_json is LOGS_OK
        elif log:
            assert cli.log == log

    # Check CliRenamer success/failure status.
    if failure:
        assert cli.failure
    elif done:
        assert cli.success
    else:
        assert not cli.done

    # Let the caller make other custom assertions.
    return (wa, outs, cli)

####
# Helper functions.
####

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

def to_tup(x):
    # Takes a value. Returns it in a tuple if its not already one.
    if isinstance(x, tuple):
        return x
    else:
        return (x,)

def pre_fmt(fmt):
    # Takes a format string.
    # Returns the portion before the first brace.
    return fmt.split('{')[0]

def can_use_clipboard():
    # I could not get pyperclip working on ubuntu in Github Actions,
    # I'm using this to bypass clipboard checks.
    return sys.platform != 'linux'

####
# Command-line arguments and options.
####

def test_version_and_help(tr, creators):
    # Exercise the command-line options that report
    # information about the app and exit immediately.

    # Paths and args.
    origs = ('a', 'b')
    news = ()
    run_args = (tr, creators, origs, news)
    kws = dict(
        include_origs = False,
        include_news = False,
        no_change = True,
        log = '',
    )

    # Version.
    wa, outs, cli = run_checks(
        *run_args,
        '--version',
        out = MF.cli_version_msg + CON.newline,
        **kws,
    )

    # Details.
    wa, outs, cli = run_checks(
        *run_args,
        '--details',
        out = BYPASS,
        **kws,
    )
    assert cli.out.split() == CLI.post_epilog.split()

    # Help.
    wa, outs, cli = run_checks(
        *run_args,
        '--help',
        out = BYPASS,
        **kws,
    )
    got = cli.out
    N = 40
    assert got.startswith(f'Usage: {CON.app_name}')
    assert CLI.description[0:N] in got
    for opt in ('--clipboard', '--paragraphs', '--rename'):
        assert f'\n  {opt}' in got
    for oc in CLI.opt_configs.values():
        assert oc.params['help'][0:N] in got

def test_indent_and_posint(tr, creators):
    # Paths and args.
    origs = ('a', 'b', 'c')
    news = ('aa', 'bb', 'cc')
    run_args = (tr, creators, origs, news)
    valid_indents = ('2', '4', '8')
    invalid_indents = ('-4', 'xx', '0', '1.2')

    # Valid indent values.
    for ind in valid_indents:
        wa, outs, cli = run_checks(
            *run_args,
            '--rename', 'return o + o',
            '--indent', ind,
            include_news = False,
            rootless = True,
        )

    # Invalid indent values.
    for ind in invalid_indents:
        wa, outs, cli = run_checks(
            *run_args,
            '--rename', 'return o + o',
            '--indent', ind,
            include_news = False,
            rootless = True,
            failure = True,
            no_change = True,
            err_in = '--indent: invalid positive_int value',
            err_starts = f'Usage: {CON.app_name}',
        )

####
# Basic renaming usage.
####

def test_basic_use_cases(tr, creators):
    # Paths and args.
    origs = ('a', 'b', 'c')
    news = ('aa', 'bb', 'cc')
    run_args = (tr, creators, origs, news)

    # Basic use cases:
    # - Flat structure as the default.
    # - Flat passed explicitly.
    # - Renaming via code.
    wa, outs, cli = run_checks(*run_args)
    wa, outs, cli = run_checks(*run_args, '--flat')
    wa, outs, cli = run_checks(
        *run_args,
        '--rename',
        'return p.with_name(p.name + p.name)',
        include_news = False,
    )

####
# Input paths and sources.
####

def test_no_input_paths(tr, creators):
    # Paths and args.
    origs = ('a', 'b', 'c')
    news = ('aa', 'bb', 'cc')
    empty_paths = ('', '   ', ' ') * 2
    run_args = (tr, creators, origs, news)

    # Initial scenario: it works.
    wa, outs, cli = run_checks(*run_args)

    # But it fails if we omit the input paths.
    wa, outs, cli = run_checks(
        *run_args,
        include_origs = False,
        include_news = False,
        failure = True,
        no_change = True,
        err_starts = MF.opts_require_one,
        err_in = CLI.sources.keys(),
    )

    # It also fails if the input paths are empty.
    wa, outs, cli = run_checks(
        *run_args,
        *empty_paths,
        include_origs = False,
        include_news = False,
        failure = True,
        no_change = True,
        err_in = PF.parsing_no_paths,
    )

def test_odd_number_inputs(tr, creators):
    # An odd number of inputs will fail.
    origs = ('z1', 'z2', 'z3')
    news = ()
    wa, outs, cli = run_checks(
        tr,
        creators,
        origs,
        news,
        failure = True,
        no_change = True,
        err_starts = pre_fmt(MF.prepare_failed_cli),
        err_in = PF.parsing_imbalance,
    )

def test_sources(tr, creators):
    # Paths and args.
    origs = ('z1', 'z2', 'z3')
    news = ('A1', 'A2', 'A3')
    extras = ('input_paths.txt',)
    run_args = (tr, creators, origs, news)

    # Create a WorkArea to get some paths in it.
    # Use them to create two constants.
    WA = creators[0](origs, news, extras = extras)
    PATHS_TEXT = CON.newline.join(WA.origs + WA.news)
    INPUTS_PATH = WA.extras[0]

    # Helpers to write PATHS_TEXT to either a file or the clipboard.
    def write_paths_to_file(wa, outs, cli):
        with open(INPUTS_PATH, 'w') as fh:
            fh.write(PATHS_TEXT)

    def write_paths_to_clipboard(wa, outs, cli):
        write_to_clipboard(PATHS_TEXT)

    # Base scenario: paths via args.
    wa, outs, cli = run_checks(
        *run_args,
        extras = extras,
    )

    # Paths via stdin.
    wa, outs, cli = run_checks(
        *run_args,
        '--stdin',
        replies = PATHS_TEXT,
        include_origs = False,
        include_news = False,
    )

    # Paths via a file.
    wa, outs, cli = run_checks(
        *run_args,
        '--file',
        INPUTS_PATH,
        extras = extras,
        include_origs = False,
        include_news = False,
        other_prep = write_paths_to_file,
    )

    # Paths via clipboard.
    if can_use_clipboard():
        wa, outs, cli = run_checks(
            *run_args,
            '--clipboard',
            include_origs = False,
            include_news = False,
            other_prep = write_paths_to_clipboard,
        )

    # Too many sources: renaming will be rejected.
    wa, outs, cli = run_checks(
        *run_args,
        '--clipboard',
        '--stdin',
        include_origs = False,
        include_news = False,
        failure = True,
        no_change = True,
        err_starts = MF.opts_mutex,
        err_in = ('--clipboard', '--stdin'),
    )

####
# The --edit and --editor options.
####

def test_edit(tr, creators):
    # Paths and args.
    origs = ('a', 'b', 'c')
    news = tuple(o + '.new' for o in origs)
    run_args = (tr, creators, origs, news)

    # Initial scenario: it works.
    wa, outs, cli = run_checks(
        *run_args,
        '--edit',
        '--editor', tr.TEST_EDITOR,
        include_news = False,
    )

    # Renaming attempt fails if we try to edit without an editor.
    wa, outs, cli = run_checks(
        *run_args,
        '--edit',
        '--editor', '',
        include_news = False,
        failure = True,
        no_change = True,
        err = MF.no_editor + '\n',
    )

    # Renaming attempt fails if the editor exits unsuccessfully.
    wa, outs, cli = run_checks(
        *run_args,
        '--edit',
        '--editor', tr.TEST_FAILER,
        include_news = False,
        failure = True,
        no_change = True,
        err_in = (
            pre_fmt(MF.editor_cmd_nonzero),
            pre_fmt(MF.edit_failed_unexpected),
        ),
    )

####
# Preferences.
####

def test_preferences_file(tr, creators):
    # Paths and args.
    origs = ('a', 'b', 'c')
    news = ('aa', 'bb', 'cc')
    run_args = (tr, creators, origs, news)

    # Scenario: an empty but valid preferences file: renaming works fine.
    wa, outs, cli = run_checks(
        *run_args,
        prefs = {},
    )

    # Scenario: an invalid JSON file.
    wa, outs, cli = run_checks(
        *run_args,
        blob = 'INVALID_JSON',
        failure = True,
        no_change = True,
        err_starts = pre_fmt(MF.prefs_reading_failed),
        err_in = 'JSONDecodeError',
    )

    # Scenario: a valid JSON file; confirm that we affect cli.opts.
    default = {}
    custom = dict(indent = 2, seq = 100, step = 10)
    exp_default = dict(indent = 4, seq = 1, step = 1)
    for prefs in (default, custom):
        wa, outs, cli = run_checks(
            *run_args,
            prefs = prefs,
            prepare_only = True,
            check_outs = False,
            done = False,
        )
        exp = prefs or exp_default
        got = {
            k : getattr(cli.opts, k)
            for k in exp
        }
        assert got == exp

    # Scenario: disable testing ENV variable and exercise the code
    # path based on the user's home directory.
    nm = CON.app_dir_env_var
    prev = os.environ[nm]
    try:
        del os.environ[nm]
        wa, outs, cli = run_checks(*run_args)
    finally:
        os.environ[nm] = prev

def test_preferences_validation(tr, creators):
    # Paths and args.
    origs = ('a', 'b', 'c')
    news = ('aa', 'bb', 'cc')
    run_args = (tr, creators, origs, news)

    # Scenario: invalid preferences keys.
    prefs = dict(indent = 2, foo = 999, bar = 'fubb')
    wa, outs, cli = run_checks(
        *run_args,
        prefs = prefs,
        prepare_only = True,
        failure = True,
        err_starts = pre_fmt(MF.invalid_pref_keys),
        err_in = ('foo', 'bar'),
    )

    # Scenario: invalid preferences value.
    # Currently, no command line options take floats, so
    # we will use that for the bad value.
    BAD_VAL = 3.14
    for oc in CLI.opt_configs.values():
        prefs = {oc.name: BAD_VAL}
        exp = MF.invalid_pref_val.format(
            oc.name,
            oc.check_value(BAD_VAL),
            BAD_VAL,
        )
        wa, outs, cli = run_checks(
            *run_args,
            prefs = prefs,
            prepare_only = True,
            failure = True,
            err = exp + '\n',
        )

def test_preferences_merging(tr, create_prefs):
    # Paths and args.
    origs = ('a', 'b')
    news = ('aa', 'bb')

    # Some user preferences that we will set.
    PREFS = dict(
        paragraphs = True,
        indent = 8,
        seq = 1000,
        step = 10,
        filter = 'return True',
        edit = True,
        editor = 'sed',
        yes = True,
        nolog = True,
        limit = 20,
        controls = ['create-parent', 'skip-equal', 'skip-recase', 'skip-same'],
    )

    # Helper to get cli.opts and confirm that CliRenamer did
    # not gripe about invalid arguments.
    def get_opts(*args):
        cli = CliRenamer(origs + news + args)
        opts = vars(cli.parse_command_line_args())
        assert not cli.done
        return opts

    # Helper to check resulting opts against expecations.
    def check_opts(got, exp1, **exp2):
        # Should have same keys as DEFAULTS.
        assert sorted(got) == sorted(DEFAULTS)
        # Check values.
        for k, def_val in DEFAULTS.items():
            exp = exp1.get(k, exp2.get(k, def_val))
            assert (k, got[k]) == (k, exp)

    # Setup: get the defaults for cli.opts.
    DEFAULTS = get_opts()

    # Scenario: an empty preferences file won't change the defaults.
    create_prefs()
    opts = get_opts()
    assert opts == DEFAULTS

    # Scenario: set some user preferences.
    # Those settings should be reflected in opts.
    create_prefs(**PREFS)
    opts = get_opts()
    check_opts(opts, PREFS)

    # Scenario: set the same preferences, but also supply some arguments on the
    # command-line. The latter should override the prefs. The overrides also
    # exercise the --disable option, which is used to unset a flag option that
    # was set true in preferences.
    OVERRIDES = dict(
        indent = 2,
        seq = 50,
        step = 5,
        filter = 'return p.suffix == ".txt"',
        editor = 'awk',
        limit = 100,
        disable = ['paragraphs', 'edit', 'yes', 'nolog'],
    )
    create_prefs(**PREFS)
    opts = get_opts(
        '--disable', *OVERRIDES['disable'],
        '--indent', '2',
        '--seq', '50',
        '--step', '5',
        '--filter', OVERRIDES['filter'],
        '--editor', 'awk',
        '--limit', '100',
    )
    check_opts(opts, OVERRIDES, controls = PREFS['controls'])

def test_preferences_problem_control(tr, creators):
    # Paths and args.
    origs = ('a', 'b', 'c')
    news = ('aa', 'bb', 'cc')
    run_args = (tr, creators, origs, news)

    # Problem controls: application defaults and some other controls.
    app_defs = list(RenamingPlan.DEFAULT_CONTROLS)
    others = ['skip-existing', 'create-parent', 'clobber-colliding']

    # Helper to get cli.opts and confirm that CliRenamer did
    # not gripe about invalid arguments.
    def get_opts(*args, failure = False):
        args = origs + news + args
        cli = CliRenamerSIO(*args)
        opts = cli.parse_command_line_args()
        if failure:
            assert cli.failure
            return (cli, opts)
        else:
            assert not cli.done
            return opts

    # Scenario: with no user-prefs and command line controls,
    # we should get the application defaults.
    opts = get_opts()
    assert sorted(opts.controls) == sorted(app_defs)

    # Scenario: defaults plus some other controls.
    opts = get_opts('--controls', *others)
    assert sorted(opts.controls) == sorted(app_defs + others)

    # Scenario: same, but also use a negative control, which
    # counteracts the application default.
    opts = get_opts('--controls', 'no-skip-equal', 'no-skip-same', 'no-skip-recase', *others)
    assert sorted(opts.controls) == sorted(others)

    # Scenario: invalid control.
    wa, outs, cli = run_checks(
        *run_args,
        '--controls', 'no-fubb',
        failure = True,
        no_change = True,
        err_in = ('--controls', 'invalid choice', 'no-fubb'),
    )
    assert cli.opts is None

    # Scenario: conflicting controls.
    wa, outs, cli = run_checks(
        *run_args,
        '--controls', 'create-parent', 'skip-parent',
        failure = True,
        no_change = True,
        err_starts = pre_fmt(MF.conflicting_controls),
        err_in = ('parent', 'create', 'skip'),
    )
    assert cli.opts is None

####
# Dryrun and no-confirmation.
####

def test_dryrun(tr, creators):
    # Paths and args.
    origs = ('a', 'b', 'c')
    news = ('aa', 'bb', 'cc')
    run_args = (tr, creators, origs, news)

    # Callable to check cli.out.
    exp_out = lambda wa, outs, cli: outs.no_action_output

    # In dryrun mode, we get the usual listing,
    # but no renaming or logging occurs.
    wa, outs, cli = run_checks(
        *run_args,
        '--rename',
        'return o + o',
        '--dryrun',
        include_news = False,
        rootless = True,
        no_change = True,
        out = exp_out,
        log = '',
    )

def test_no_confirmation(tr, creators):
    # Paths and args.
    origs = ('a', 'b', 'c')
    news = ('aa', 'bb', 'cc')
    run_args = (tr, creators, origs, news)

    # Callable to check cli.out.
    exp_out = lambda wa, outs, cli: outs.no_confirm_output

    # If user does not confirm, we get the usual listing,
    # but no renaming or logging occurs.
    wa, outs, cli = run_checks(
        *run_args,
        '--rename',
        'return o + o',
        include_news = False,
        rootless = True,
        no_change = True,
        out = exp_out,
        log = '',
        yes = False,
    )

####
# User-supplied code.
####

def test_rename_paths_raises(tr, creators):
    # Paths, etc.
    origs = ('z1', 'z2', 'z3')
    news = ('ZZ1', 'ZZ2', 'ZZ3')
    expecteds = news[:1] + origs[1:]
    NSTART = RenamingPlan.TRACKING.not_started
    run_args = (tr, creators, origs, news)

    # Helper to format expected error text for subsequent checks.
    def exp_err_text(tracking_index):
        msg = MF.renaming_raised.format(tracking_index)
        return '\n' + msg.strip().split(CON.colon)[0]

    # Helpers to call do_prepare() and do_rename() in various ways.
    def other_prep1(wa, outs, cli):
        cli.do_prepare()
        cli.do_prepare()
        assert cli.plan.tracking_rp is None
        cli.do_rename()
        assert cli.plan.tracking_rp is None
        cli.do_rename()
        assert cli.plan.tracking_rp is None

    def other_prep2(wa, outs, cli):
        cli.do_prepare()
        cli.plan.has_renamed = True
        cli.do_rename()

    def other_prep3(wa, outs, cli):
        cli.do_prepare()
        assert cli.plan.tracking_rp is None
        assert cli.plan.tracking_index == NSTART
        cli.plan.raise_at = N
        cli.do_rename()

    # Basic scenario.
    wa, outs, cli = run_checks(*run_args)

    # Same thing, but using do_prepare() and do_rename().
    wa, outs, cli = run_checks(
        *run_args,
        rename_via_do = True,
    )

    # Same thing, but we can call those methods multiple times.
    wa, outs, cli = run_checks(
        *run_args,
        skip_rename = True,
        other_prep = other_prep1,
    )

    # Same scenario, but we will set plan.has_renamed to trigger
    # an exception when plan.rename_paths() is called.
    wa, outs, cli = run_checks(
        *run_args,
        skip_rename = True,
        other_prep = other_prep2,
        failure = True,
        no_change = True,
        err_starts = exp_err_text(NSTART),
        err_in = 'raise MvsError(MF.rename_done_already)',
        out = BYPASS,
        log = LOGS_OK,
    )
    assert cli.plan.tracking_index == NSTART
    assert cli.out.rstrip() == outs.paths_to_be_renamed.rstrip()

    # Same scenario, but this time we will trigger the exception via
    # the raise_at attribute, so we can check the tracking_index in
    # the tracking log and in the command-line error message.
    N = 1
    wa, outs, cli = run_checks(
        *run_args,
        expecteds = expecteds,
        skip_rename = True,
        other_prep = other_prep3,
        failure = True,
        err_starts = exp_err_text(N),
        err_in = 'ZeroDivisionError: SIMULATED_ERROR',
        out = BYPASS,
        log = LOGS_OK,
    )
    assert cli.plan.tracking_rp.orig == wa.origs[N]
    assert cli.plan.tracking_index == N
    assert cli.log_tracking_dict == dict(tracking_index = N)
    assert cli.out.rstrip() == outs.paths_to_be_renamed.rstrip()

def test_filter_all(tr, creators):
    # Paths and args.
    origs = ('a', 'b', 'c')
    news = ('aa', 'bb', 'cc')
    run_args = (tr, creators, origs, news)

    # Initial scenario: it works.
    wa, outs, cli = run_checks(*run_args)

    # Scenario: renaming attempt fails if the user code filters everything.
    wa, outs, cli = run_checks(
        *run_args,
        '--filter',
        'return False',
        failure = True,
        no_change = True,
        err_starts = pre_fmt(MF.prepare_failed_cli),
        err_in = PF.all_filtered,
    )

####
# Textual outputs.
####

def test_log(tr, creators):
    # Paths and args.
    origs = ('a', 'b', 'c')
    news = ('aa', 'bb', 'cc')
    run_args = (tr, creators, origs, news)

    # A basic renaming scenario.
    # We can load its logging data and check that both dicts
    # contain expected some of the expected keys and/or vals.
    wa, outs, cli = run_checks(*run_args)
    d1 = cli.log_plan_dict
    d2 = cli.log_tracking_dict
    assert d1['version'] == __version__
    for k in ('current_directory', 'opts', 'inputs', 'rename_pairs', 'problems'):
        assert k in d1
    assert d2 == dict(tracking_index = cli.plan.TRACKING.done)

def test_pagination(tr, creators):
    # Paths and args.
    origs = tuple(ascii_lowercase)
    news = tuple(o + o for o in origs)
    run_args = (tr, creators, origs, news)

    # Callable to check cli.out.
    exp_out = lambda wa, outs, cli: '\n' + outs.paths_renamed

    # A scenario to exercise the paginate() function.
    wa, outs, cli = run_checks(
        *run_args,
        pager = tr.TEST_PAGER,
        out = exp_out,
    )

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

def test_some_failed_rps(tr, creators):
    # Paths and args.
    origs = ('z1', 'z2', 'z3', 'z4')
    news = ('A1', 'A2', 'A3', 'A4')
    extras = ('A1', 'A2')
    expecteds = ('z1', 'z2', 'A3', 'A4') + extras
    run_args = (tr, creators, origs, news)

    # Create a WorkArea just to get some paths that we need later.
    WA = creators[0](origs, news)

    # Initial scenario: two of the new paths already exist.
    # No renaming occurs.
    wa, outs, cli = run_checks(
        *run_args,
        extras = extras,
        no_change = True,
        failure = True,
        err_starts = pre_fmt(MF.prepare_failed_cli),
        err_in = PF.existing,
    )

    # Scenario: skip the items with problems.
    # Renaming works.
    wa, outs, cli = run_checks(
        *run_args,
        '--controls', 'skip-existing',
        extras = extras,
        expecteds = expecteds,
        outs_origs = WA.origs[2:],
        outs_news = WA.news[2:],
    )

    # Scenario: pass conflict failure-control options.
    # No renaming occurs.
    wa, outs, cli = run_checks(
        *run_args,
        '--controls', 'skip-existing', 'clobber-existing',
        extras = extras,
        no_change = True,
        failure = True,
        err_starts = pre_fmt(MF.conflicting_controls),
        err_in = (CONTROLS.skip, CONTROLS.clobber),
    )

####
# Miscellaneous.
####

def test_wrapup_with_tb(tr, create_wa):
    # Excercises all calls of wrapup_with_tb() and checks for expected
    # attribute changes. Most of those code branches (1) are a hassle to reach
    # during testing, (2) are unlikely to occur in real usage, (3) do nothing
    # interesting other than call the method tested here, and thus (4) are
    # pragma-ignored by test-coverage. Here we simple exercise the machinery to
    # insure against MF attribute names or format strings becoming outdated.

    # Paths.
    origs = ('z1', 'z2', 'z3')
    news = ('A1', 'A2', 'A3')

    # Format strings and dummy params they can use.
    fmts = (
        ('', MF.plan_creation_failed),
        (99, MF.renaming_raised),
        ('PATH', MF.prefs_reading_failed),
        ('', MF.path_collection_failed),
        ('', MF.edit_failed_unexpected),
        ('', MF.log_writing_failed),
    )

    # Check all the format strings.
    for param, fmt in fmts:
        # Create WorkArea and CliRenamer.
        # Initially, the latter is not done.
        wa = create_wa(origs, news)
        cli = CliRenamerSIO(*wa.origs, *wa.news)
        assert cli.exit_code is None
        assert cli.done is False

        # Call wrapup_with_tb().
        msg = fmt.format(param) if param else fmt
        cli.wrapup_with_tb(msg)

        # Now the CliRenamer is done and its error
        # output is what we expect.
        assert cli.exit_code == CON.exit_fail
        assert cli.done is True
        assert cli.out == ''
        assert cli.log == ''
        assert pre_fmt(fmt) in cli.err
        wa.check(no_change = True)

