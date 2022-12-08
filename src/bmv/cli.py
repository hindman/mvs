import argparse
import json
import re
import string
import subprocess
import sys
import traceback

from datetime import datetime
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

def main(args = None, file_sys = None):
    # Parse and validate command-line arguments.
    args = sys.argv[1:] if args is None else args
    opts = handle_exit(parse_command_line_args(args))

    # Collect the input paths.
    inputs = collect_input_paths(opts)

    # Initialize RenamingPlan.
    plan = RenamingPlan(
        inputs = inputs,
        rename_code = opts.rename,
        structure = get_structure(opts),
        seq_start = opts.seq,
        seq_step = opts.step,
        filter_code = opts.filter,
        indent = opts.indent,
        file_sys = file_sys,
        **fail_controls_kws(opts),
    )

    # Prepare the RenamingPlan and halt if it failed.
    plan.prepare()
    if plan.failed:
        msg = FAIL.prepare_failed_cli.format(plan.first_failure.msg)
        halt(CON.exit_fail, msg)

    # Print the renaming listing.
    listing = listing_msg(plan.rps, opts.limit, 'Paths to be renamed{}.\n')
    paginate(listing, opts.pager)

    # Stop if dryrun mode.
    if opts.dryrun:
        halt(CON.exit_ok, CON.no_action_msg)

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

####
# Command-line argument handling.
####

def parse_command_line_args(args):
    ap, opts = parse_args(args)
    if opts.help:
        text = 'U' + ap.format_help()[1:]
        return ExitCondition(text)
    elif opts.version:
        return ExitCondition(f'{CON.app_name} v{__version__}')
    else:
        return validated_failure_controls(
            validated_options(opts),
            opts_mode = True,
        )

def parse_args(args):
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
    opts = ap.parse_args(args)
    return (ap, opts)

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

def handle_exit(x):
    if isinstance(x, Failure):
        halt(CON.exit_fail, x.msg)
    elif isinstance(x, ExitCondition):
        halt(CON.exit_ok, x.msg)
    else:
        return x

####
# Utilities: listings, pagination, and logging.
####

def paginate(text, pager_cmd):
    if pager_cmd:
        p = subprocess.Popen(pager_cmd, stdin = subprocess.PIPE, shell = True)
        p.stdin.write(text.encode(CON.encoding))
        p.communicate()
    else:
        print(text)

def listing_msg(xs, limit, msg_fmt):
    tallies = tallies_msg(xs, limit, msg_fmt)
    xs_limited = xs if limit is None else xs[0:limit]
    if xs_limited:
        items = CON.newline.join(x.formatted for x in xs_limited)
        return f'{tallies}\n{items}'
    else:
        return tallies_msg

def tallies_msg(xs, limit, msg_fmt):
    n = len(xs)
    lim = n if limit is None else limit
    tallies = f' (total {n}, listed {lim})'
    return msg_fmt.format(tallies)

def collect_logging_data(opts, plan):
    d = dict(
        version = __version__,
        current_directory = str(Path.cwd()),
        opts = vars(opts),
    )
    d.update(**plan.as_dict)
    return d

def write_to_json_file(path, d):
    with open(path, 'w') as fh:
        json.dump(d, fh, indent = 4)

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

def get_confirmation(prompt, expected = 'y'):
    r = input(prompt + f' [{expected}]? ').lower().strip()
    return r == expected

def halt(code = None, msg = None):
    code = CON.exit_ok if code is None else code
    fh = sys.stderr if code else sys.stdout
    if msg:
        nl = CON.newline
        msg = msg if msg.endswith(nl) else msg + nl
        fh.write(msg)
    sys.exit(code)

def fail_controls_kws(opts):
    return {
        k : getattr(opts, k)
        for k in CONTROLLABLES.keys()
    }

