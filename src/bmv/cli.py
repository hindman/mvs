import argparse
import re
import subprocess
import sys

from dataclasses import dataclass
from itertools import groupby
from pathlib import Path
from textwrap import dedent

'''

General code reorg/cleanup:

    - Organize code into sections.
    - Ditto for tests.
    - misc/notes

'''

####
# Constants.
####

class CON:
    newline = '\n'
    tab = '\t'
    exit_ok = 0
    exit_fail = 1
    renamer_name = 'do_rename'
    default_pager_cmd = 'less'
    encoding = 'utf-8'

    # CLI configuration.
    description = (
        'Renames or moves files in bulk, via user-supplied Python '
        'code or a data source mapping old paths to new paths.'
    )
    epilog = (
        'The user-supplied renaming code has access to the original file path as a str [variable: o], '
        'its pathlib.Path representation [variable: p], '
        'and the following Python libraries or classes [re, Path]. '
        'It should explicitly return the desired new path, either as a str or a Path. '
        'The code should omit indentation on its first line, but must provide it for subsequent lines.'
    )
    names = 'names'
    opts_config = (
        # Sources for input paths.
        {
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
        # Other options.
        {
            names: '--dryrun -d',
            'action': 'store_true',
            'help': 'List renamings without performing them',
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
    )

    # Format for user-supplied renaming code.
    renamer_code_fmt = dedent('''
        def {renamer_name}(o, p):
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

@dataclass
class RenamePair:
    orig: str
    new: str

    @property
    def formatted(self):
        return f'{self.orig}\n{self.new}\n'

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
# Entry point.
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

def parse_inputs(opts, inputs):
    # Handle --rename option: just original paths.
    if opts.rename:
        return (tuple(inputs), None)

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

    # Return as tuples.
    return (tuple(origs), tuple(news))

def limited(xs, n):
    # Takes sequence and returns a limited form of it.
    return xs if n is None else xs[0:n]

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

def main(args = None):
    # Parse and validate command-line arguments.
    opts = parse_args(sys.argv[1:] if args is None else args)
    catch_failure(validate_options(opts))

    # Get the input paths and parse them to assemble the original and new paths.
    inputs = get_input_paths(opts)
    origs, news = catch_failure(parse_inputs(opts, inputs))

    # If user supplied renaming code, use it to generate new paths.
    if opts.rename:
        renamer = make_renamer_func(opts.rename, opts.indent)
        news = [
            catch_failure(compute_new_path(renamer, o))
            for o in origs
        ]

    # Bundle the original and new paths into RenamePair instances.
    rps = tuple(RenamePair(orig, new) for orig, new in zip(origs, news))

    # Validate the renaming plan.
    fails = validate_rename_pairs(rps)
    if fails:
        msg = items_to_text(fails, opts.limit, 'Renaming validation failures{}.\n')
        paginate(msg, opts.pager)
        halt(CON.exit_fail, CON.no_action_msg)

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

    # Rename.
    msg = listing_msg(rps, opts.limit, 'Paths to be renamed{}.')
    print(msg)
    halt(CON.exit_ok, 'RENAMING WOULD HAVE OCCURRED')     # TODO: remove.
    for rp in rps:
        Path(rp.orig).rename(rp.new)

def listing_msg(items, limit, msg_fmt):
    n = len(items)
    lim = n if limit is None else limit
    counts_msg = f' (total {n}, listed {lim})'
    return msg_fmt.format(counts_msg)

def compute_new_path(renamer, orig):
    # Run the user-supplied code to get the new path.
    try:
        new = renamer(orig, Path(orig))
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

def get_confirmation(prompt, expected = 'y'):
    r = input(prompt + f' [{expected}]? ').lower().strip()
    return r == expected

def parse_args(args):
    ap = argparse.ArgumentParser(
        description = CON.description,
        epilog = CON.epilog,
    )
    for oc in CON.opts_config:
        kws = dict(oc)
        xs = kws.pop(CON.names).split()
        ap.add_argument(*xs, **kws)
    opts = ap.parse_args(args)
    return opts

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

def make_renamer_func(user_code, indent = 4):
    # Define the text of the renamer code.
    code = CON.renamer_code_fmt.format(
        renamer_name = CON.renamer_name,
        indent = ' ' * indent,
        user_code = user_code,
    )
    # Create the renamer function via exec() in the context of:
    # - Globals that we want to make available to the user's code.
    # - A locals dict that we can use to return the generated function.
    globs = dict(re = re, Path = Path)
    locs = {}
    exec(code, globs, locs)
    return locs[CON.renamer_name]

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
    fails.extend(
        RenamePairFailure(CON.fail_new_exists, rp)
        for rp in rps
        if Path(rp.new).exists()
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

####
# Utilities.
####

def halt(code = None, msg = None):
    code = CON.exit_ok if code is None else code
    fh = sys.stderr if code else sys.stdout
    if msg:
        nl = CON.newline
        msg = msg if msg.endswith(nl) else msg + nl
        fh.write(msg)
    sys.exit(code)

