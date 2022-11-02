import argparse
import json
import re
import string
import subprocess
import sys

from dataclasses import asdict
from datetime import datetime
from itertools import cycle
from pathlib import Path
from textwrap import dedent

from .version import __version__
from .constants import CON, CLI, FAIL, STRUCTURES
from .plan import RenamingPlan
from .data_objects import (
    Failure,
    OptsFailure,
    ExitCondition,
)


'''

# GET ARGS.
# Flow: take input; compute. Might halt intentionally or due to error: usage, I/O.
Parse command-line args.
Handle special opts: --help --version [can quit]
Validate opts [can error]

# INPUT PATHS => VALID, FILTERED RPS.
# Flow: compute. Might halt due to error: usage, user-code, I/O.
Collect input paths.
Parse input paths. [can fail or error; produces full or partial rps]
Filter rps [can fail]
Execute user's renaming code [can fail; at this point rps are full]
Validate rps, contingent on opts [can fail or error; can further filter rps]

# LIST, CONFIRM, LOG.
# Flow: I/O. Might halt intentionally or due to error: I/O.
List the renamings, unless suppressed by opts.
Stop if dryrun mode.
Get user confirmation, unless suppressed by opts.
Log the renamings [can fail]

# RENAME.
# Flow: I/O. Might halt due to error: I/O.
Rename paths [can fail]

===============

Where does nontrivial I/O occur?

    Read inputs: can handle outside of RenamingPlan.
    Filter paths: user code [see below].
    Generate new paths: user code [see below].
    Validate rps: various existence checks for ORIG and NEW paths.
    Rename paths: would be bypassed during testing.

    Note on user code:
        - In real usage, the code could interact with file system.
        - For my testing purposes, such scenarios need not be explored.

How to execute user code for renaming and filtering:

    Creating the function:

        Generate code from indent and user's code str.
        During generation, supply only constants via globs [re, Path].

    Function signature:

        func(o, p, seq, plan)
            o = rp.orig
            p = Path(rp.orig)
            seq_val = current sequence value
            plan = RenamingPlan

            # The plan can provide access to wider state, notably a method
            # to strip common prefixes from the rps. For example:
            return plan.strip_prefix(o)

    Executing the function:

        Initialize seq.

        for rp in rps:
            seq_val = next(seq)
            try:
                result = func(rp.orig, Path(rp.orig), seq_val, self)
            except Exception as e:
                ...
            Either retain rp (filtering) or set rp.new (renaming).

===============

RenamingPlan()
    inputs: collection[str]
    rename: func or str[CODE]
    structure: None or enum[para,flat,pairs,rows]
    seq_start: int
    seq_step: int
    skip_equal: bool
    filter: func or str[CODE]
    indent: int
    ----
    file_sys: collection[str]
    ----
    dryrun: bool                  # Not needed: plan.prepare() does everything except the renaming.

main()
    Parse command-line args.
    Handle special opts: --help --version
    Validate opts

        opts = handle_exit(parse_command_line_args(...))         # Test separately.

    Collect input paths.

        inputs = handle_exit(collect_input_paths(opts))          # Test separately.

    Parse, filter, generate new paths, validate rps:

        plan = RenamingPlan(...)
        plan.prepare()
        if plan.failed:
            # Report and halt.

        # Notes:
        #   - The plan.prepare() call does not raise.
        #   - Rather, it computes and validates.
        #   - Assemble as much Failure information as possible.

    List the renamings, handle dryrun, confirm, log, rename:

        listing = plan.renaming_listing()                         # Test separately.
        print(listing)
        if opts.dryrun:
            halt()
        elif opts.yes or confirm(...):
            if not opts.nolog:
                plan_data = plan.as_dict()                        # Test separately.
                log_data = collect_logging_data(opts, plan_data)  # Test separately.
                write_to_logfile(opts, log_data)
            try:
                plan.rename_paths()
            except Exception as e:
                ...

    RenamingPlan: testing usage:

        plan = RenamingPlan(..., file_sys = FILE_SYSTEM)          # Inject file system dependency.
        plan.prepare()
        assert ...                                                # Assert against plan state.

    RenamingPlan: direct library usage:

        plan = RenamingPlan(...)
        try:
            plan.rename_paths()
        except Exception as e:
            ...

    Input path sources:
      ARGV
      --clipboard
      --stdin
      --file PATH
    Input path structures:
      --rename CODE
      --paragraphs
      --flat
      --pairs
      --rows
    Listings:
      --pager CMD
      --limit N
    Sequence numbers:
      --seq N
      --step N
    Other:
      --help
      --version
      --skip-equal
      --dryrun, -d
      --nolog
      --yes
      --indent N
      --filter CODE

'''

####
# Entry point.
####

def main(args = None):
    # Parse and validate command-line arguments.
    args = sys.argv[1:] if args is None else args
    opts = handle_exit(parse_command_line_args(args))

    # Collect the input paths.
    inputs = collect_input_paths(opts)
    # TODO: Failure if no inputs (eg input-text with all blank lines).

    # Initialize RenamingPlan.
    plan = RenamingPlan(
        inputs = inputs,
        rename_code = opts.rename,
        structure = get_structure(opts),
        seq_start = opts.seq,
        seq_step = opts.step,
        # skip_equal = opts.skip_equal,
        filter_code = opts.filter,
        indent = opts.indent,
    )

    plan.prepare()
    if plan.failed:
        pass

    print('PLAN failed?', plan.failed)
    return

    #=======================

    # Get the input paths and parse them to get RenamePair instances.
    rps = catch_failure(parse_inputs(opts, inputs))

    # If user supplied filtering code, use it to filter the paths.
    if opts.filter:
        rps = catch_failure(filtered_rename_pairs(rps, opts))

    # If user supplied renaming code, use it to generate new paths.
    if opts.rename:
        renamer = make_user_defined_func('rename', opts, rps)
        seq = sequence_iterator(opts.seq, opts.step)
        for rp in rps:
            rp.new = catch_failure(compute_new_path(renamer, rp.orig, next(seq)))

    # Skip RenamePair instances with equal paths.
    if opts.skip_equal:
        rps = [rp for rp in rps if rp.orig != rp.new]

    # Validate the renaming plan.
    if rps:
        fails = validate_rename_pairs(rps)
        if fails:
            msg = items_to_text(fails, opts.limit, 'Renaming validation failures{}.\n')
            paginate(msg, opts.pager)
            halt(CON.exit_fail, CON.no_action_msg)
    else:
        msg = 'No paths to be renamed.'
        halt(CON.exit_fail, msg)

    #=======================

    # List the renamings.
    if opts.dryrun or not opts.yes:
        msg = items_to_text(rps, opts.limit, 'Paths to be renamed{}.\n')
        paginate(msg, opts.pager)

    # Stop if dryrun mode.
    if opts.dryrun:
        halt(CON.exit_ok, CON.no_action_msg)

    # User confirmation.
    if not opts.yes:
        msg = listing_msg(rps, opts.limit, '\nRename paths{}')
        if get_confirmation(msg, expected = 'yes'):
            print()
        else:
            halt(CON.exit_ok, CON.no_action_msg)

    # Log the renamings.
    if not opts.nolog:
        log_renamings(logging_metadata(opts, rps))

    # Rename.
    for rp in rps:
        Path(rp.orig).rename(rp.new)

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
        return validated_options(opts)

def parse_args(args):
    ap = argparse.ArgumentParser(
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
    gen = (s for s in STRUCTURES.keys() if getattr(opts, s))
    return next(gen, None)

def collect_input_paths(opts):
    # Get the input path text from the source.
    # Returns a tuple of stripped lines.
    if opts.paths:
        paths = opts.paths
    else:
        text = (
            read_from_clipboard() if opts.clipboard else
            read_from_file(opts.file) if opts.file else
            sys.stdin.read()
        )
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

def items_to_text(xs, limit, msg_fmt):
    prefix = listing_msg(xs, limit, msg_fmt)
    limited = xs if limit is None else xs[0:limit]
    if limited:
        msg = CON.newline.join(x.formatted for x in limited)
        return f'{prefix}\n{msg}'
    else:
        return prefix

def listing_msg(items, limit, msg_fmt):
    n = len(items)
    lim = n if limit is None else limit
    counts_msg = f' (total {n}, listed {lim})'
    return msg_fmt.format(counts_msg)

def logging_metadata(opts, rps):
    return dict(
        version = __version__,
        current_directory = str(Path.cwd()),
        opts = vars(opts),
        rename_pairs = [asdict(rp) for rp in rps],
    )

def log_renamings(d):
    path = log_file_path()
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
# Utilities: user confirmation, quitting, etc.
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

