import argparse
import json
import re
import string
import subprocess
import sys
import traceback

from datetime import datetime
from io import StringIO
from itertools import cycle
from pathlib import Path
from textwrap import dedent

from .version import __version__
from .plan import RenamingPlan
from .constants import (
    CON,
    CLI,
    FAIL,
    STRUCTURES,
    CONTROLLABLES,
    validated_failure_controls,
)
from .data_objects import (
    Failure,
    OptsFailure,
    ExitCondition,
)

####
# Entry point.
####

def main(args = None):
    args = sys.argv[1:] if args is None else args
    cli = CliRenamer(args)
    cli.run()
    sys.exit(cli.exit_code)

class CliRenamer:

    def __init__(self,
                 args,
                 file_sys = None,
                 stdout = sys.stdout,
                 stderr = sys.stderr,
                 stdin = sys.stdin,
                 logfh = None):

        # Store constructor arguments.
        self.args = args
        self.file_sys = file_sys
        self.stdout = stdout
        self.stderr = stderr
        self.stdin = stdin
        self.logfh = logfh

        # Other attributes that will be set by run().
        self.opts = None
        self.inputs = None
        self.plan = None
        self.exit_msg = None
        self.exit_code = None

    def run(self):

        # Parse args.
        self.opts = self.handle_exit(parse_command_line_args(self.args))
        opts = self.opts
        if self.done:
            return

        ###############################################################################

        # Collect the input paths.
        self.inputs = collect_input_paths(self.opts)

        # Initialize RenamingPlan.
        self.plan = RenamingPlan(
            inputs = self.inputs,
            rename_code = opts.rename,
            structure = get_structure(opts),
            seq_start = opts.seq,
            seq_step = opts.step,
            filter_code = opts.filter,
            indent = opts.indent,
            file_sys = self.file_sys,
            **fail_controls_kws(opts),
        )
        plan = self.plan

        # Prepare the RenamingPlan and halt if it failed.
        plan.prepare()
        if plan.failed:
            msg = FAIL.prepare_failed_cli.format(plan.first_failure.msg)
            self.stderr.write(with_newline(msg))
            self.exit_code = CON.exit_fail
            return

        # Print the renaming listing.
        listing = listing_msg('Paths to be renamed{}.\n', plan.rps, opts.limit)
        self.paginate(listing)

        # Stop if dryrun mode.
        if opts.dryrun:
            self.stdout.write(with_newline(CON.no_action_msg))
            self.exit_code = CON.exit_ok
            return

        # User confirmation.
        if not opts.yes:
            msg = msg_with_tallies('\nRename paths{}', plan.rps, opts.limit)
            if not self.get_confirmation(msg, expected = 'yes'):
                self.stdout.write(with_newline(CON.no_action_msg))
                self.exit_code = CON.exit_ok
                return

        # Log the renamings.
        if not opts.nolog:
            log_data = collect_logging_data(opts, plan)
            self.write_to_json_file(log_file_path(), log_data)

        # Rename.
        try:
            plan.rename_paths()
            self.exit_code = CON.exit_ok
            self.stdout.write(with_newline(CON.paths_renamed_msg))
        except Exception as e:
            self.exit_code = CON.exit_fail
            tb = traceback.format_exc()
            msg = FAIL.renaming_raised.format(tb)
            self.stderr.write(with_newline(msg))

    ####
    # Command-line argument handling.
    ####

    @property
    def done(self):
        return self.exit_code is not None

    def handle_exit(self, x):
        if isinstance(x, Failure):
            self.exit_code = CON.exit_fail
            self.stderr.write(with_newline(x.msg))
        elif isinstance(x, ExitCondition):
            self.exit_code = CON.exit_ok
            self.stdout.write(with_newline(x.msg))
        return x

    def paginate(self, text):
        if self.opts.pager:
            p = subprocess.Popen(self.opts.pager, stdin = subprocess.PIPE, shell = True)
            p.stdin.write(text.encode(CON.encoding))
            p.communicate()
        else:
            self.stdout.write(text)

    def get_confirmation(self, prompt, expected = 'y'):
        msg = prompt + f' [{expected}]? '
        self.stdout.write(msg)
        reply = self.stdin.readline().lower().strip()
        return reply == expected

    def write_to_json_file(self, path, d):
        with open(path, 'w') as fh:
            json.dump(d, self.logfh or fh, indent = 4)

####
# Collecting input paths.
####

def get_structure(opts):
    gen = (s for s in STRUCTURES.keys() if getattr(opts, s, None))
    return next(gen, None)

def collect_input_paths(opts):
    # Get the input path text from the source.
    # Returns a tuple of stripped lines.
    if opts.paths:
        paths = opts.paths
    else:
        if opts.clipboard:
            text = read_from_clipboard()
        elif opts.file:
            text = read_from_file(opts.file)
        else:
            text = sys.stdin.read()
        paths = text.split(CON.newline)
    return tuple(path.strip() for path in paths)

####
# Utilities: listings, pagination, and logging.
####

def msg_with_tallies(fmt, xs, limit):
    # Returns a message followed by two counts in parentheses:
    # N items; and N items listed based on opts.limit.
    n = len(xs)
    lim = n if limit is None else limit
    tallies = f' (total {n}, listed {lim})'
    return fmt.format(tallies)

def listing_msg(fmt, xs, limit):
    # Returns a message-with-tallies followed by a potentially-limited
    # listing of RenamePair paths.
    msg = msg_with_tallies(fmt, xs, limit)
    items = CON.newline.join(x.formatted for x in xs[0:limit])
    return f'{msg}\n{items}'

def collect_logging_data(opts, plan):
    d = dict(
        version = __version__,
        current_directory = str(Path.cwd()),
        opts = vars(opts),
    )
    d.update(**plan.as_dict)
    return d

def log_file_path():
    home = Path.home()
    subdir = '.' + CON.app_name
    now = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
    return Path.home() / subdir / (now + '.json')

####
# Utilities: reading from or writing to files, clipboard, etc.
####

def read_from_file(path):
    with open(path) as fh:
        return fh.read()

def read_from_clipboard():
    cp = subprocess.run(
        ['pbpaste'],
        capture_output = True,
        check = True,
        text = True,
    )
    return cp.stdout

def write_to_clipboard(text):
    subprocess.run(
        ['pbcopy'],
        check = True,
        text = True,
        input = text,
    )

####
# Utilities: other.
####

def fail_controls_kws(opts):
    return {
        k : getattr(opts, k)
        for k in CONTROLLABLES.keys()
    }

def with_newline(msg):
    nl = CON.newline
    return msg if msg.endswith(nl) else msg + nl

def parse_command_line_args(args):
    # Create the parser.
    ap = create_arg_parser()

    # Try to parse args. In event of parsing failure, argparse tries to exit
    # with usage plus error message. We capture that output to standard error
    # in a StringIO and return the text in a Failure instance.
    try:
        real_stderr = sys.stderr
        sys.stderr = StringIO()
        opts = ap.parse_args(args)
    except SystemExit as e:
        msg = sys.stderr.getvalue()
        return Failure(msg)
    finally:
        sys.stderr = real_stderr

    # Deal with special options that will lead to an early, successful exit.
    if opts.help:
        text = 'U' + ap.format_help()[1:]
        return ExitCondition(text)
    elif opts.version:
        text = f'{CON.app_name} v{__version__}'
        return ExitCondition(text)

    # Otherwise return the opts if they pass validations. If not,
    # we will return a Failure.
    return validated_failure_controls(
        validated_options(opts),
        opts_mode = True,
    )

def create_arg_parser():
    ap = argparse.ArgumentParser(
        prog = CON.app_name,
        description = CLI.description,
        epilog = CLI.epilog,
        add_help = False,
    )
    g = None
    for oc in CLI.opts_config:
        kws = dict(oc)
        if CLI.group in kws:
            g = ap.add_argument_group(kws.pop(CLI.group))
        xs = kws.pop(CLI.names).split()
        g.add_argument(*xs, **kws)
    return ap

def validated_options(opts):
    # Define the option checks.
    checks = (
        # Exactly one source for input paths.
        (CLI.sources.keys(), False),
        # Zero or one option specifying an input structure.
        (CLI.structures.keys(), True),
    )
    # Run the checks, all of which return OptsFailure or None.
    for opt_names, zero_ok in checks:
        result = check_opts_require_one(opts, opt_names, zero_ok)
        if result:
            return result
    # Success.
    return opts

def check_opts_require_one(opts, opt_names, zero_ok):
    used = tuple(
        nm for nm in opt_names
        if getattr(opts, nm, None)
    )
    n = len(used)
    if n == 0 and zero_ok:
        return None
    elif n == 0:
        return create_opts_failure(opt_names, FAIL.opts_require_one)
    elif n == 1:
        return None
    else:
        return create_opts_failure(opt_names, FAIL.opts_mutex)

def create_opts_failure(opt_names, base_msg):
    joined = ', '.join(
        ('' if nm == CLI.sources.paths else '--') + nm
        for nm in opt_names
    )
    return OptsFailure(f'{base_msg}: {joined}')

