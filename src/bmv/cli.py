import sys
import argparse
import re
from collections import Counter
from pathlib import Path


'''

Next:

    Data objects:

        - for user code
        - for old/new pairs

    Output style:

        - for dryrun
        - for error reporting

Behaviors:

    Input mechanism: old-paths via ARGS.
    Validations.
    Dryrun mode.

        bmv [--dryrun] --rename 'return ...' --old ...

'''

####
# Constants.
####

class Constants:
    newline = '\n'
    exit_ok = 0
    exit_fail = 1
    replacer_name = 'do_replace'

    # CLI configuration.
    names = 'names'
    opts_config = (
        {
            names: '--old -o',
            'nargs': '+',
            'metavar': 'PATH',
        },
        {
            names: '--rename -r',
            'metavar': 'CODE',
        },
        {
            names: '--dryrun -d',
            'action': 'store_true',
        },
    )

CON = Constants()

####
# Entry point.
####

def main(args = None):
    args = sys.argv[1:] if args is None else args
    ap, opts = parse_args(args)
    
    # Generate new paths.
    olds = opts.old
    replacer = make_replacer_func(opts.rename)
    news = list(map(replacer, olds))

    # TODO: improve validation output:
    # - Show both old and new path where useful.
    # - Show all errors where feasible.

    # Validate: old-path and new-path differ for each pair.
    for old, new in zip(olds, news):
        if old == new:
            fail_validation(f'Old path and new path are the same: {old} {new}')

    # Validate: old-paths exist.
    for old in olds:
        if not Path(old).exists():
            fail_validation(f'Old path does not exist: {old}')

    # Validate: new-paths do not exist.
    for new in news:
        if Path(new).exists():
            fail_validation(f'New path exists: {new}')

    # Validate: new-paths do not collide among themselves.
    for new, count in Counter(news).items():
        if count > 1:
            fail_validation(f'Collision among new paths: {new}')

    # Validate: directories of the new-paths exist.
    for new in news:
        if not Path(new).parent.exists():
            fail_validation(f'Parent directory of new path does not exist: {new}')

    # Dry run mode: print and stop.
    if opts.dryrun:
        for o, n in zip(olds, news):
            print()
            print(o)
            print(n)
        return

    # Rename.
    print('Not implemented: renaming')

def parse_args(args):
    ap = argparse.ArgumentParser()
    for oc in CON.opts_config:
        kws = dict(oc)
        xs = kws.pop(CON.names).split()
        ap.add_argument(*xs, **kws)
    opts = ap.parse_args(args)
    return (ap, opts)

def make_replacer_func(user_code, i = 4):
    indent = ' ' * i
    code = f'def {CON.replacer_name}(old):\n{indent}{user_code}\n'
    globs = dict(
        re = re,
    )
    locs = {}
    exec(code, globs, locs)
    return locs[CON.replacer_name]

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

