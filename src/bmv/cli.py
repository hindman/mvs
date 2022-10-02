import sys
import argparse
import re
from collections import Counter
from pathlib import Path
from textwrap import dedent
from dataclasses import dataclass
from itertools import groupby
import subprocess

'''

parse_inputs():
    - finish writing tests

main(): rework the execution of the user-supplied renaming code

options: add --delimiter  [tab for rows]

catch_failure(x, multiple = False): add ability to handle a sequence of failures.

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

    # CLI configuration.
    description = 'Renames or moves files in bulk, via user-supplied Python code.'
    epilog = (
        'The user-supplied renaming code has access to the original file path as a str [variable: o], '
        'its pathlib.Path representation [variable: p], '
        'and the following Python libraries or classes [re, Path]. '
        'It should explicitly return the desired new path, either as a str or a Path. '
        'The code should omit indentation on its first line, but must provide it for subsequent lines.'
    )
    names = 'names'
    opts_config = (
        {
            names: '--original -o',
            'nargs': '+',
            'metavar': 'PATH',
            'help': 'Original file paths',
        },
        {
            names: '--rename -r',
            'metavar': 'CODE',
            'help': 'Code to convert original path to new path',
        },
        {
            names: '--indent',
            'type': int,
            'metavar': 'N',
            'default': 4,
            'help': 'Number of spaces for indentation in user-supplied code',
        },
        {
            names: '--stdin',
            'action': 'store_true',
            'help': 'Input paths via STDIN',
        },
        {
            names: '--clipboard',
            'action': 'store_true',
            'help': 'Input paths via the clipboard',
        },
        {
            names: '--file',
            'metavar': 'PATH',
            'help': 'Input paths via a text file',
        },
        {
            names: '--paragraphs',
            'action': 'store_true',
            'help': 'Input paths in paragraphs: originals, blank line, then news',
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
        {
            names: '--yes',
            'action': 'store_true',
            'help': 'Rename files without user confirmation step',
        },
        {
            names: '--dryrun -d',
            'action': 'store_true',
            'help': 'List renamings without performing them',
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
    fail_parsing_opts = 'Unexpected options during parsing: no --original or structures given'
    fail_invalid_row = 'The --rows option expects rows with exactly two cells: {row!r}'
    fail_invalid_paragraphs = 'The --paragraphs option expects exactly two paragraphs'
    fail_parsing_inequality = 'Got an unequal number of original paths and new paths'
    fail_opts_conflicts = 'The --{attr} option should not be used with'
    fail_opts_mutex = 'Options should not be used with each other'
    fail_opts_require_one = 'At least one of these options should be used'

    no_action_msg = '\nNo action taken.'

    listing_batch_size = 10

    opts_sources = ('stdin', 'file', 'clipboard')
    opts_structures = ('paragraphs', 'pairs', 'rows')

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
class RenamePairFailure(Failure):
    rp: RenamePair

    @property
    def formatted(self):
        return f'{self.msg}:\n{self.rp.formatted}'

def catch_failure(x):
    if isinstance(x, Failure):
        quit(code = CON.exit_fail, msg = x.msg)
    else:
        return x

####
# Entry point.
####

def get_input_paths(opts):
    if opts.original:
        return tuple(opts.original)
    else:
        text = (
            read_from_clipboard() if opts.clipboard else
            read_from_file(opts.file) if opts.file else
            sys.stdin.read()
        )
        return tuple(
            line.strip()
            for line in text.split(CON.newline)
        )

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
    # Handle --original option: just original paths.
    if opts.original:
        return (tuple(opts.original), None)

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
            return ParseFailure(CON.fail_invalid_paragraphs)
    elif opts.pairs:
        # Pairs: original path, new path, original path, etc.
        origs = []
        news = []
        for i, line in enumerate(inputs):
            (news if i % 2 else origs).append(line)
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
                    return ParseFailure(CON.fail_invalid_row.format(row = row))
    else:
        return ParseFailure(CON.fail_parsing_opts)

    # Stop if we got unqual numbers of paths.
    if len(origs) != len(news):
        return ParseFailure(CON.fail_parsing_inequality)

    # Return as tuples.
    return (tuple(origs), tuple(news))

def main(args = None):
    # Parse arguments and get original paths.
    opts = parse_args(sys.argv[1:] if args is None else args)

    # Validate options.
    catch_failure(validate_options(opts))

    # Get the input paths.
    inputs = get_input_paths(opts)

    # Parse inputs to assemble the original-new pairs:
    origs, news = catch_failure(parse_inputs(opts, inputs))

    print([inputs])
    quit()

    # Create the renamer function based on the user-supplied code.
    renamer = make_renamer_func(opts.rename, opts.indent)

    # Use that function to generate the new paths.
    origs = tuple(opts.original)
    news = []
    for o in origs:
        try:
            news.append(renamer(o, Path(o)))
        except Exception as e:
            msg = f'Error in user-supplied renaming code: {e} [original path: {o}]'
            quit(CON.exit_fail, msg)

    # Confirm that those new paths have a valid data type.
    for i, new in enumerate(news):
        if isinstance(new, (str, Path)):
            news[i] = str(new)
        else:
            typ = type(new).__name__
            msg = f'Invalid type from user-supplied renaming code: {typ} [original path: {o}]'
            quit(CON.exit_fail, msg)
            news.append(new)

    # Bundle the orig-new paths into RenamePair instances.
    rps = tuple(RenamePair(orig, new) for orig, new in zip(origs, news))

    # Validation.
    fails = validate_rename_pairs(rps)
    if fails:
        for f in fails:
            print(f.formatted)
        quit(code = CON.exit_fail)

    # Dry run mode: print and stop.
    if opts.dryrun:
        for rp in rps:
            print(rp.formatted)
        return

    # User confirmation.
    if not opts.yes:
        # Listing.
        for i, rp in enumerate(rps):
            if i > 0 and i % CON.listing_batch_size == 0:
                if not get_confirmation('Continue listing', expected = 'y'):
                    break
                print()
            print(rp.formatted)
        # Confirmation.
        if not get_confirmation('Rename files', expected = 'yes'):
            quit(CON.exit_ok, CON.no_action_msg)
        print()

    # Rename.
    for rp in rps:
        Path(rp.orig).rename(rp.new)

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
    # Define each check as a function and its arguments.
    checks = (
        # Don't used --original or --rename with incompatible options.
        (check_opts_conflicts, opts, 'original', CON.opts_sources),
        (check_opts_conflicts, opts, 'original', CON.opts_structures),
        (check_opts_conflicts, opts, 'rename', CON.opts_structures),
        # Don't use multiple source or structures.
        (check_opts_mutex, opts, CON.opts_sources),
        (check_opts_mutex, opts, CON.opts_structures),
        # Use --original or a source option; use --rename or a structure option.
        (check_opts_require_one, opts, ('original',) + CON.opts_sources),
        (check_opts_require_one, opts, ('rename',) + CON.opts_structures),
    )
    # Run the checks, all of which return OptsFailure or None.
    for func, *xs in checks:
        result = func(*xs)
        if result:
            return result
    return None

def check_opts_conflicts(opts, attr, ks):
    # Do not use opts.ATTR with any opts.K.
    if getattr(opts, attr, None):
        used = tuple(k for k in ks if getattr(opts, k, None))
        if used:
            return bad_opts_failure(used, CON.fail_opts_conflicts.format(attr = attr))
    return None

def check_opts_mutex(opts, ks):
    # Do not use multiple opts.K.
    used = tuple(k for k in ks if getattr(opts, k, None))
    return (
        None if len(used) <= 1 else
        bad_opts_failure(used, CON.fail_opts_mutex)
    )

def check_opts_require_one(opts, ks):
    # Use at least one of opts.K.
    used = tuple(k for k in ks if getattr(opts, k, None))
    return (
        None if used else
        bad_opts_failure(ks, CON.fail_opts_require_one)
    )

def bad_opts_failure(opt_names, base_msg):
    joined = ', '.join(f'--{nm}' for nm in opt_names)
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

    # Original should exist.
    fails.extend(
        RenamePairFailure(CON.fail_orig_missing, rp)
        for rp in rps
        if not Path(rp.orig).exists()
    )

    # New should not exist.
    fails.extend(
        RenamePairFailure(CON.fail_new_exists, rp)
        for rp in rps
        if Path(rp.new).exists()
    )

    # Parent of new should exist.
    fails.extend(
        RenamePairFailure(CON.fail_new_parent_missing, rp)
        for rp in rps
        if not Path(rp.new).parent.exists()
    )

    # Original and new should differ.
    fails.extend(
        RenamePairFailure(CON.fail_orig_new_same, rp)
        for rp in rps
        if rp.orig == rp.new
    )

    # News should not collide among themselves.
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

def quit(code = None, msg = None):
    code = CON.exit_ok if code is None else code
    fh = sys.stderr if code else sys.stdout
    if msg:
        nl = CON.newline
        msg = msg if msg.endswith(nl) else msg + nl
        fh.write(msg)
    sys.exit(code)

