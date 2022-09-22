import sys
import argparse
import re
from collections import Counter
from pathlib import Path
from textwrap import dedent
from dataclasses import dataclass

'''

Initial implementation:

    bmv [--dryrun] --rename 'return ...' --old ...

    Input mechanism: old-paths via ARGS.
    Validations.
    Dryrun mode.

Next:

    User code: provide access to a Path instance.
    Handle execeptions raised by user code.
    Handle invalid data types return by user code (allow str or Path).

    Implement renaming behavior.

    Usage text.

    Tests for validations.

TODO:

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

    replacer_code_fmt = dedent('''
        def {replacer_name}(old):
        {indent}{user_code}
    ''').lstrip()

CON = Constants()

@dataclass
class RenamePair:
    old: str
    new: str

    @property
    def formatted(self):
        return f'{self.old}\n{self.new}\n'

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
    args = sys.argv[1:] if args is None else args
    ap, opts = parse_args(args)
    
    # Generate new paths.
    olds = tuple(opts.old)
    replacer = make_replacer_func(opts.rename)
    news = tuple(map(replacer, olds))
    rps = tuple(RenamePair(old, new) for old, new in zip(olds, news))

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
    # Define the text of the replacer code.
    code = CON.replacer_code_fmt.format(
        replacer_name = CON.replacer_name,
        indent = ' ' * i,
        user_code = user_code,
    )
    # Create the replacer function via exec() in the context of:
    # - Globals that we want to make available to the user's code.
    # - A locals dict that we can use to return the generated function.
    globs = dict(re = re)
    locs = {}
    exec(code, globs, locs)
    return locs[CON.replacer_name]

def validate_rename_pairs(rps):
    fails = []

    # Organize rps into dict-of-list, keyed by new.
    grouped_by_new = {}
    for rp in rps:
        grouped_by_new.setdefault(str(rp.new), []).append(rp)

    # Old should exist.
    fails.extend(
        ValidationFailure(rp, 'Old path does not exist')
        for rp in rps
        if not Path(rp.old).exists()
    )

    # New should not exist.
    fails.extend(
        ValidationFailure(rp, 'New path exists')
        for rp in rps
        if Path(rp.new).exists()
    )

    # Parent of new should exist.
    fails.extend(
        ValidationFailure(rp, 'Parent directory of new path does not exist')
        for rp in rps
        if not Path(rp.new).parent.exists()
    )

    # Old and new should differ.
    fails.extend(
        ValidationFailure(rp, 'Old path and new path are the same')
        for rp in rps
        if rp.old == rp.new
    )

    # News should not collide among themselves.
    fails.extend(
        ValidationFailure(rp, 'New path collides with another new path')
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

