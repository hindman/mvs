import argparse
import json
import re
import string
import subprocess
import sys

from dataclasses import dataclass, asdict
from datetime import datetime
from itertools import cycle
from itertools import groupby
from os.path import commonprefix
from pathlib import Path
from textwrap import dedent

from .version import __version__
from .constants import CON, CLI, FAIL, STRUCTURES
from .plan import RenamingPlan

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
            plan.rename_paths()

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

    # Initialize RenamingPlan.
    plan = RenamingPlan(
        inputs = inputs,
        rename_code = opts.rename,
        structure = get_structure(opts),
        seq_start = opts.seq,
        seq_step = opts.step,
        skip_equal = opts.skip_equal,
        filter_code = opts.filter,
        indent = opts.indent,
    )

    # Prepare: parse inputs; filter inputs; compute new paths; validate plan.
    try:
        plan.prepare()
    except Exception as e:
        # parsing: ParseFailure
        # filtering: FilterFailure
        # renaming: RenameFailure
        # validation: RenamePairFailure
        #
        # If all of the steps currently return a Failure rather than raising,
        # we could do this:
        #
        #   handle_exit(plan.prepare())
        #
        # But that seems inconsistent with how one would expect a library to work.
        #
        # How to reconcile things.
        #
        #   # Preparing never raises. It merely computes, validates, and returns
        #   # either None or a Failure instance.
        #   result = plan.prepare()
        #
        #   # But renaming can raise if the preparations resulted in a Failure.
        #
        pass

    print(opts)
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

# def exit_if_help_requested(ap, opts):
#     if opts.help:
#         text = ap.format_help()
#         halt(CON.exit_ok, 'U' + text[1:])
#     elif opts.version:
#         text = f'{CON.app_name} v{__version__}'
#         halt(CON.exit_ok, text)

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

def parse_inputs(opts, inputs):
    # Handle --rename option: just original paths.
    if opts.rename:
        return tuple(
            RenamePair(orig, None)
            for orig in inputs
        )

    # Otherwise, organize inputs into original paths and new paths.
    if opts.paragraphs:
        # Paragraphs: first original paths, then new paths.
        groups = [
            list(lines)
            for g, lines in groupby(inputs, key = bool)
            if g
        ]
        if len(groups) == 2:
            origs, news = groups
        else:
            return ParseFailure(FAIL.parsing_paragraphs)
    elif opts.flat:
        # Flat: like paragraphs without the blank-line delimiter.
        paths = [line for line in inputs if line]
        i = len(paths) // 2
        origs, news = (paths[0:i], paths[i:])
    elif opts.pairs:
        # Pairs: original path, new path, original path, etc.
        origs = []
        news = []
        current = origs
        for line in inputs:
            if line:
                current.append(line)
                current = news if current is origs else origs
    elif opts.rows:
        # Rows: original-new path pairs, as tab-delimited rows.
        origs = []
        news = []
        for row in inputs:
            if row:
                cells = row.split(CON.tab)
                if len(cells) == 2:
                    origs.append(cells[0])
                    news.append(cells[1])
                else:
                    return ParseFailure(FAIL.parsing_row.format(row = row))
    else:
        return ParseFailure(FAIL.parsing_opts)

    # Stop if we got unqual numbers of paths.
    if len(origs) != len(news):
        return ParseFailure(FAIL.parsing_inequality)

    # Return the RenamePair instances.
    return tuple(
        RenamePair(orig, new)
        for orig, new in zip(origs, news)
    )

####
# Path filtering.
####

def filtered_rename_pairs(rps, opts):
    func = make_user_defined_func('filter', opts, rps)
    seq = sequence_iterator(opts.seq, opts.step)
    filtered = []
    for rp in rps:
        seq_val = next(seq)
        result = filter_path(func, rp.orig, seq_val)
        if isinstance(result, FilterFailure):
            return result
        elif result:
            filtered.append(rp)
    return filtered

def filter_path(filterer, orig, seq_val):
    # Run the user-supplied filtering code.
    try:
        return bool(filterer(orig, Path(orig), seq_val))
    except Exception as e:
        msg = f'Error in user-supplied filtering code: {e} [original path: {orig}]'
        return FilterFailure(msg)

####
# Path renaming.
####

@dataclass
class RenamePair:
    # A data object to hold an original path and the corresponding new path.
    orig: str
    new: str

    @property
    def formatted(self):
        return f'{self.orig}\n{self.new}\n'

def compute_new_path(renamer, orig, seq_val):
    # Run the user-supplied code to get the new path.
    try:
        new = renamer(orig, Path(orig), seq_val)
    except Exception as e:
        msg = f'Error in user-supplied renaming code: {e} [original path: {orig}]'
        return RenameFailure(msg)

    # Validate its type and return.
    if isinstance(new, str):
        return new
    elif isinstance(new, Path):
        return str(new)
    else:
        typ = type(new).__name__
        msg = f'Invalid type from user-supplied renaming code: {typ} [original path: {orig}]'
        return RenameFailure(msg)

def validate_rename_pairs(rps):
    fails = []

    # Organize rps into dict-of-list, keyed by new.
    grouped_by_new = {}
    for rp in rps:
        grouped_by_new.setdefault(str(rp.new), []).append(rp)

    # Original paths should exist.
    fails.extend(
        RenamePairFailure(FAIL.orig_missing, rp)
        for rp in rps
        if not Path(rp.orig).exists()
    )

    # New paths should not exist.
    # The failure is conditional on ORIG and NEW being different
    # to avoid pointless reporting of multiple failures in such cases.
    fails.extend(
        RenamePairFailure(FAIL.new_exists, rp)
        for rp in rps
        if rp.orig != rp.new and Path(rp.new).exists()
    )

    # Parent of new path should exist.
    fails.extend(
        RenamePairFailure(FAIL.new_parent_missing, rp)
        for rp in rps
        if not Path(rp.new).parent.exists()
    )

    # Original path and new path should differ.
    fails.extend(
        RenamePairFailure(FAIL.orig_new_same, rp)
        for rp in rps
        if rp.orig == rp.new
    )

    # New paths should not collide among themselves.
    fails.extend(
        RenamePairFailure(FAIL.new_collision, rp)
        for group in grouped_by_new.values()
        for rp in group
        if len(group) > 1
    )

    return fails

def make_user_defined_func(action, opts, rps):
    # Define the text of the code.
    func_name = f'do_{action}'
    code = CON.user_code_fmt.format(
        func_name = func_name,
        user_code = getattr(opts, action),
        indent = ' ' * opts.indent,
    )
    # Create the function via exec() in the context of:
    # - Globals that we want to make available to the user's code.
    # - A locals dict that we can use to return the generated function.
    globs = dict(
        re = re,
        Path = Path,
        strip_prefix = make_prefix_stripper(rps),
    )
    locs = {}
    exec(code, globs, locs)
    return locs[func_name]

def make_prefix_stripper(rps):
    origs = tuple(rp.orig for rp in rps)
    i = len(commonprefix(origs))
    return lambda x: x[i:] if i else x

####
# Failure handling.
####

@dataclass
class Failure:
    msg: str

@dataclass
class OptsFailure(Failure):
    pass

@dataclass
class ParseFailure(Failure):
    pass

@dataclass
class RenameFailure(Failure):
    pass

@dataclass
class FilterFailure(Failure):
    pass

@dataclass
class RenamePairFailure(Failure):
    rp: RenamePair

    @property
    def formatted(self):
        return f'{self.msg}:\n{self.rp.formatted}'

@dataclass
class ExitCondition:
    msg: str

# def catch_failure(x):
#     if isinstance(x, Failure):
#         halt(CON.exit_fail, x.msg)
#     else:
#         return x

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

def sequence_iterator(start, step):
    return iter(range(start, sys.maxsize, step))

