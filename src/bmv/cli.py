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

from . import __version__

'''

'''

####
# Entry point.
####

def main(args = None):

    # Parse and validate command-line arguments.
    ap, opts = parse_args(sys.argv[1:] if args is None else args)
    exit_if_help_requested(ap, opts)
    catch_failure(validate_options(opts))

    # Get the input paths and parse them to get RenamePair instances.
    inputs = get_input_paths(opts)
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
    halt(CON.exit_ok, 'Renaming currently DISABLED')
    for rp in rps:
        Path(rp.orig).rename(rp.new)

####
# Command-line argument handling.
####

def parse_args(args):
    ap = argparse.ArgumentParser(
        description = CON.description,
        epilog = CON.epilog,
        add_help = False,
    )
    g = None
    for oc in CON.opts_config:
        kws = dict(oc)
        if CON.group in kws:
            g = ap.add_argument_group(kws.pop(CON.group))
        xs = kws.pop(CON.names).split()
        g.add_argument(*xs, **kws)
    opts = ap.parse_args(args)
    return (ap, opts)

def validate_options(opts):
    # Define the option checks.
    checks = (
        # Exactly one source for input paths.
        (CON.opts_sources, False),
        # Zero or one option specifying an input structure.
        (CON.opts_structures, True),
    )
    # Run the checks, all of which return OptsFailure or None.
    for opt_names, zero_ok in checks:
        result = check_opts_require_one(opts, opt_names, zero_ok)
        if result:
            return result
    return None

def check_opts_require_one(opts, opt_names, zero_ok):
    used = tuple(
        nm for nm in opt_names
        if getattr(opts, nm, None)
    )
    n = len(used)
    if n == 0 and zero_ok:
        return None
    elif n == 0:
        return create_opts_failure(opt_names, CON.fail_opts_require_one)
    elif n == 1:
        return None
    else:
        return create_opts_failure(opt_names, CON.fail_opts_mutex)

def create_opts_failure(opt_names, base_msg):
    joined = ', '.join(
        ('' if nm == CON.opts_paths else '--') + nm
        for nm in opt_names
    )
    return OptsFailure(f'{base_msg}: {joined}')

def exit_if_help_requested(ap, opts):
    if opts.help:
        text = ap.format_help()
        halt(CON.exit_ok, 'U' + text[1:])

####
# Collecting input paths.
####

def get_input_paths(opts):
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
            return ParseFailure(CON.fail_parsing_paragraphs)
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
                    return ParseFailure(CON.fail_parsing_row.format(row = row))
    else:
        return ParseFailure(CON.fail_parsing_opts)

    # Stop if we got unqual numbers of paths.
    if len(origs) != len(news):
        return ParseFailure(CON.fail_parsing_inequality)

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
        RenamePairFailure(CON.fail_orig_missing, rp)
        for rp in rps
        if not Path(rp.orig).exists()
    )

    # New paths should not exist.
    # The failure is conditional on ORIG and NEW being different
    # to avoid pointless reporting of multiple failures in such cases.
    fails.extend(
        RenamePairFailure(CON.fail_new_exists, rp)
        for rp in rps
        if rp.orig != rp.new and Path(rp.new).exists()
    )

    # Parent of new path should exist.
    fails.extend(
        RenamePairFailure(CON.fail_new_parent_missing, rp)
        for rp in rps
        if not Path(rp.new).parent.exists()
    )

    # Original path and new path should differ.
    fails.extend(
        RenamePairFailure(CON.fail_orig_new_same, rp)
        for rp in rps
        if rp.orig == rp.new
    )

    # New paths should not collide among themselves.
    fails.extend(
        RenamePairFailure(CON.fail_new_collision, rp)
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

def catch_failure(x):
    if isinstance(x, Failure):
        halt(CON.exit_fail, x.msg)
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

####
# Constants.
####

class CON:
    newline = '\n'
    tab = '\t'
    exit_ok = 0
    exit_fail = 1
    renamer_name = 'do_rename'
    filterer_name = 'do_filter'
    default_pager_cmd = 'less'
    encoding = 'utf-8'

    # CLI configuration.
    app_name = 'bmv'
    description = '''
        Renames or moves files in bulk, via user-supplied Python
        code or a data source mapping old paths to new paths.
    '''
    epilog = '''
        The user-supplied renaming and filtering code has access to the
        original file path as a str [variable: o], its pathlib.Path
        representation [variable: p], the current sequence value [variable:
        seq], some Python libraries or classes [re, Path], and some utility
        functions [strip_prefix]. The functions should explicitly return a
        value: for renaming code, the desired new path, either as a str or a
        Path; for filtering code, any true value to retain the original path or
        any false value to reject it. The code should omit indentation on its
        first line, but must provide it for subsequent lines. For reference,
        some useful Path components: p.parent, p.name, p.stem, p.suffix.
    '''
    names = 'names'
    group = 'group'
    opts_config = (
        # Sources for input paths.
        {
            group: 'Input path sources',
            names: 'paths',
            'nargs': '*',
            'metavar': 'PATH',
            'help': 'Input file paths',
        },
        {
            names: '--clipboard',
            'action': 'store_true',
            'help': 'Input paths via the clipboard',
        },
        {
            names: '--stdin',
            'action': 'store_true',
            'help': 'Input paths via STDIN',
        },
        {
            names: '--file',
            'metavar': 'PATH',
            'help': 'Input paths via a text file',
        },
        # Options defining the structure of the input path data.
        {
            group: 'Input path structures',
            names: '--rename -r',
            'metavar': 'CODE',
            'help': 'Code to convert original path to new path',
        },
        {
            names: '--paragraphs',
            'action': 'store_true',
            'help': 'Input paths in paragraphs: original paths, blank line, new paths',
        },
        {
            names: '--flat',
            'action': 'store_true',
            'help': 'Input paths in non-delimited paragraphs: original paths, then new',
        },
        {
            names: '--pairs',
            'action': 'store_true',
            'help': 'Input paths in line pairs: original, new, original, new, etc.',
        },
        {
            names: '--rows',
            'action': 'store_true',
            'help': 'Input paths in tab-delimited rows: original, tab, new',
        },
        # Pagination options.
        {
            group: 'Listings',
            names: '--pager',
            'metavar': 'CMD',
            'default': default_pager_cmd,
            'help': (
                'Command string for paginating listings [default: '
                f'`{default_pager_cmd}`; empty string to disable]'
            ),
        },
        {
            names: '--limit',
            'metavar': 'N',
            'type': int,
            'help': 'Upper limit on the number of items to display in listings [default: none]',
        },
        # Sequence numbers.
        {
            group: 'Sequence numbers',
            names: '--seq',
            'metavar': 'N',
            'type': int,
            'default': 1,
            'help': 'Sequence start value [default: 1]',
        },
        {
            names: '--step',
            'metavar': 'N',
            'type': int,
            'default': 1,
            'help': 'Sequence step value [default: 1]',
        },
        # Other options.
        {
            group: 'Other',
            names: '--help -h',
            'action': 'store_true',
            'help': 'Display this help message and exit',
        },
        {
            names: '--skip-equal',
            'action': 'store_true',
            'help': 'Skip renamings with equal paths rather than reporting as errors',
        },
        {
            names: '--dryrun -d',
            'action': 'store_true',
            'help': 'List renamings without performing them',
        },
        {
            names: '--nolog',
            'action': 'store_true',
            'help': 'Suppress logging',
        },
        {
            names: '--yes',
            'action': 'store_true',
            'help': 'Rename files without a user confirmation step',
        },
        {
            names: '--indent',
            'type': int,
            'metavar': 'N',
            'default': 4,
            'help': 'Number of spaces for indentation in user-supplied code',
        },
        {
            names: '--filter',
            'metavar': 'CODE',
            'help': 'Code to filter input paths',
        },
    )

    # Format for user-supplied renaming code.
    user_code_fmt = dedent('''
        def {func_name}(o, p, seq):
        {indent}{user_code}
    ''').lstrip()

    fail_orig_missing = 'Original path does not exist'
    fail_new_exists = 'New path exists'
    fail_new_parent_missing = 'Parent directory of new path does not exist'
    fail_orig_new_same = 'Original path and new path are the same'
    fail_new_collision = 'New path collides with another new path'
    fail_parsing_opts = 'Unexpected options during parsing: no paths or structures given'
    fail_parsing_row = 'The --rows option expects rows with exactly two cells: {row!r}'
    fail_parsing_paragraphs = 'The --paragraphs option expects exactly two paragraphs'
    fail_parsing_inequality = 'Got an unequal number of original paths and new paths'
    fail_opts_require_one = 'One of these options is required'
    fail_opts_mutex = 'No more than one of these options should be used'

    no_action_msg = '\nNo action taken.'

    listing_batch_size = 10

    opts_paths = 'paths'
    opts_sources = (opts_paths, 'stdin', 'file', 'clipboard')
    opts_structures = ('rename', 'paragraphs', 'flat', 'pairs', 'rows')

