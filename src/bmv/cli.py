import sys
import argparse

####
# Constants.
####

class Constants:
    newline = '\n'
    exit_ok = 0
    exit_fail = 1

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
    print(opts)

def parse_args(args):
    ap = argparse.ArgumentParser()
    for oc in CON.opts_config:
        kws = dict(oc)
        xs = kws.pop(CON.names).split()
        ap.add_argument(*xs, **kws)
    opts = ap.parse_args(args)
    return (ap, opts)

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

