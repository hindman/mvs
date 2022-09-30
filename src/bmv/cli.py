import sys
import argparse
import re
from collections import Counter
from pathlib import Path
from textwrap import dedent
from dataclasses import dataclass

'''

Get the input paths:

    --original

    OR one of:
        --clipboard
        --file
        --stdin

Parse inputs to assemble original-new pairs:

    --rename

    OR one of:

    --paragraphs
    --pairs
    --rows

    If --rename:
        - Input text consists of just orig-paths.

Refactor validate_options():
    - return data rather than quitting
    - write tests

'''

####
# Constants.
####

class CON:
    newline = '\n'
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

    no_action_msg = '\nNo action taken.'

    listing_batch_size = 10

@dataclass
class RenamePair:
    orig: str
    new: str

    @property
    def formatted(self):
        return f'{self.orig}\n{self.new}\n'

@dataclass
class ValidationFailure:
    rp: RenamePair
    msg: str

    @property
    def formatted(self):
        return f'{self.msg}:\n{self.rp.formatted}'

####
# Entry point.
####

def main(args = None):
    # Parse arguments and get original paths.
    args = sys.argv[1:] if args is None else args
    opts = parse_args(args)

    # Validate options.
    validate_options(opts)

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
    sources = ('stdin', 'file', 'clipboard')
    structures = ('paragraphs', 'pairs', 'rows')
    original = ('original',)
    rename = ('rename',)
    # Don't used --original or --rename with incompatible options.
    check_opts_conflicts(opts, original[0], sources)
    check_opts_conflicts(opts, original[0], structures)
    check_opts_conflicts(opts, rename[0], structures)
    # Don't use multiple source or structures.
    check_opts_mutex(opts, sources)
    check_opts_mutex(opts, structures)
    # Use --original or a source option; use --rename or a structure option.
    check_opts_require_one(opts, original + sources)
    check_opts_require_one(opts, rename + structures)

def check_opts_conflicts(opts, attr, ks):
    # Do not use opts.ATTR with any opts.K.
    if getattr(opts, attr):
        used = tuple(k for k in ks if getattr(opts, k))
        if used:
            quit_with_bad_opts(used, f'The --{attr} option should not be used with')

def check_opts_mutex(opts, ks):
    # Do not use multiple opts.K.
    used = tuple(k for k in ks if getattr(opts, k))
    if len(used) > 1:
        quit_with_bad_opts(used, f'Options should not be used with each other')

def check_opts_require_one(opts, ks):
    # Use at least one of opts.K.
    used = tuple(k for k in ks if getattr(opts, k))
    if not used:
        quit_with_bad_opts(ks, f'At least one of these options should be used')

def quit_with_bad_opts(opt_names, base_msg):
    joined = ', '.join(f'--{nm}' for nm in opt_names)
    quit(code = CON.exit_fail, msg = f'{base_msg}: {joined}')

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
        ValidationFailure(rp, CON.fail_orig_missing)
        for rp in rps
        if not Path(rp.orig).exists()
    )

    # New should not exist.
    fails.extend(
        ValidationFailure(rp, CON.fail_new_exists)
        for rp in rps
        if Path(rp.new).exists()
    )

    # Parent of new should exist.
    fails.extend(
        ValidationFailure(rp, CON.fail_new_parent_missing)
        for rp in rps
        if not Path(rp.new).parent.exists()
    )

    # Original and new should differ.
    fails.extend(
        ValidationFailure(rp, CON.fail_orig_new_same)
        for rp in rps
        if rp.orig == rp.new
    )

    # News should not collide among themselves.
    fails.extend(
        ValidationFailure(rp, CON.fail_new_collision)
        for group in grouped_by_new.values()
        for rp in group
        if len(group) > 1
    )

    return fails

####
# Utilities.
####

def fail_validation(msg):
    quit(CON.exit_fail, msg)

def quit(code = None, msg = None):
    code = CON.exit_ok if code is None else code
    fh = sys.stderr if code else sys.stdout
    if msg:
        nl = CON.newline
        msg = msg if msg.endswith(nl) else msg + nl
        fh.write(msg)
    sys.exit(code)

