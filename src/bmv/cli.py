import argparse
import json
import re
import string
import subprocess
import sys
import traceback

from datetime import datetime
from io import StringIO
from itertools import cycle
from pathlib import Path
from textwrap import dedent

from .problems import Problem, PROBLEM_FORMATS as PF
from .plan import RenamingPlan
from .version import __version__
from .constants import CON, CLI, STRUCTURES
from .utils import read_from_clipboard, read_from_file, write_to_clipboard
from .data_objects import BmvError

####
# Entry point.
####

def main(args = None):
    args = sys.argv[1:] if args is None else args
    cli = CliRenamer(args)
    cli.run()
    sys.exit(cli.exit_code)

####
# A class to do the work of main() in way amenable to testing.
####

class CliRenamer:

    def __init__(self,
                 args,
                 file_sys = None,
                 stdout = sys.stdout,
                 stderr = sys.stderr,
                 stdin = sys.stdin,
                 logfh = None):

        # Attributes received as arguments.
        self.args = args
        self.file_sys = file_sys
        self.stdout = stdout
        self.stderr = stderr
        self.stdin = stdin
        self.logfh = logfh

        # Data attributes that will be set during do_prepare().
        self.opts = None
        self.inputs = None
        self.plan = None

        # Status tracking attributes.
        self.exit_code = None
        self.has_prepared = False
        self.has_renamed = False

    def run(self):
        self.do_prepare()
        if not self.done:
            self.do_rename()

    def do_prepare(self):
        # Don't execute more than once.
        if self.has_prepared:
            return
        else:
            self.has_prepared = True

        # Parse args.
        self.opts = self.parse_command_line_args()
        if self.done:
            return
        else:
            opts = self.opts

        # Collect the input paths.
        self.inputs = self.collect_input_paths()
        if self.done:
            return

        # Initialize the RenamingPlan.
        try:
            self.plan = RenamingPlan(
                inputs = self.inputs,
                rename_code = opts.rename,
                structure = self.get_structure(),
                seq_start = opts.seq,
                seq_step = opts.step,
                filter_code = opts.filter,
                indent = opts.indent,
                file_sys = self.file_sys,
                skip = opts.skip,
                clobber = opts.clobber,
                create = opts.create,
            )
            plan = self.plan
        except BmvError as e:
            self.wrapup(CON.exit_fail, e.msg)
            return
        except Exception as e:
            tb = traceback.format_exc()
            msg = PF.plan_creation_failed.format(tb)
            self.wrapup(CON.exit_fail, msg)
            return

        # Prepare the RenamingPlan and halt if it failed.
        plan.prepare()
        if plan.failed:
            msg = self.listing_msg(PF.prepare_failed_cli, plan.uncontrolled_problems)
            self.wrapup(CON.exit_fail, msg)
            return

        # Print the renaming listing.
        listing = self.listing_msg('Paths to be renamed{}.\n', plan.rps)
        self.paginate(listing)

        # Stop if dryrun mode.
        if opts.dryrun:
            self.wrapup(CON.exit_ok, CON.no_action_msg)
            return

        # User confirmation.
        if not opts.yes:
            msg = self.msg_with_tallies('\nRename paths{}', plan.rps)
            if not self.get_confirmation(msg, expected = 'yes'):
                self.wrapup(CON.exit_ok, CON.no_action_msg)
                return

        # Log the renamings.
        if not opts.nolog:
            self.write_to_json_file(self.log_file_path, self.log_data)

    def do_rename(self):
        # Don't execute more than once.
        if self.has_renamed:
            return
        else:
            self.has_renamed = True

        # Rename paths.
        try:
            self.plan.rename_paths()
            self.wrapup(CON.exit_ok, CON.paths_renamed_msg)
        except Exception as e:
            tb = traceback.format_exc()
            msg = PF.renaming_raised.format(tb)
            self.wrapup(CON.exit_fail, msg)

    def wrapup(self, code, msg):
        # Helper for do_prepare() and do_rename().
        # Writes a newline-terminated message and sets exit_code.
        fh = self.stdout if code == CON.exit_ok else self.stderr
        msg = msg if msg.endswith(CON.newline) else msg + CON.newline
        fh.write(msg)
        self.exit_code = code

    ####
    # Command-line argument handling.
    ####

    @property
    def done(self):
        return self.exit_code is not None

    def paginate(self, text):
        if self.opts.pager:
            p = subprocess.Popen(self.opts.pager, stdin = subprocess.PIPE, shell = True)
            p.stdin.write(text.encode(CON.encoding))
            p.communicate()
        else:
            self.stdout.write(text)

    def get_confirmation(self, prompt, expected = 'y'):
        msg = prompt + f' [{expected}]? '
        self.stdout.write(msg)
        reply = self.stdin.readline().lower().strip()
        return reply == expected

    def write_to_json_file(self, path, d):
        try:
            with open(path, 'w') as fh:
                json.dump(d, self.logfh or fh, indent = 4)
        except Exception as e:
            tb = traceback.format_exc()
            msg = PF.log_writing_failed.format(tb)
            self.wrapup(CON.exit_fail, msg)

    def collect_input_paths(self):
        # Get the input path text from the source.
        # Returns a tuple of stripped lines.
        opts = self.opts
        if opts.paths:
            paths = opts.paths
        else:
            try:
                if opts.clipboard:
                    text = read_from_clipboard()
                elif opts.file:
                    text = read_from_file(opts.file)
                else:
                    text = self.stdin.read()
            except Exception as e:
                tb = traceback.format_exc()
                msg = PF.path_collection_failed.format(tb)
                self.wrapup(CON.exit_fail, msg)
                return None
            paths = text.split(CON.newline)
        return tuple(path.strip() for path in paths)

    def msg_with_tallies(self, fmt, xs):
        # Returns a message followed by two counts in parentheses:
        # N items; and N items listed based on opts.limit.
        n = len(xs)
        lim = n if self.opts.limit is None else self.opts.limit
        tallies = f' (total {n}, listed {lim})'
        return fmt.format(tallies)

    def listing_msg(self, fmt, xs):
        # Returns a message-with-tallies followed by a potentially-limited
        # listing of RenamePair paths.
        msg = self.msg_with_tallies(fmt, xs)
        items = CON.newline.join(x.formatted for x in xs[0:self.opts.limit])
        return f'{msg}\n{items}'

    def parse_command_line_args(self):
        # Create the parser.
        ap = self.create_arg_parser()

        # Use argparse to parse self.args.
        #
        # In event of parsing failure, argparse tries to exit
        # with usage plus error message. We capture that output
        # to standard error in a StringIO so we can emit the output
        # via our own machinery.
        try:
            real_stderr = sys.stderr
            sys.stderr = StringIO()
            opts = ap.parse_args(self.args)
        except SystemExit as e:
            msg = sys.stderr.getvalue()
            self.wrapup(CON.exit_fail, msg)
            return None
        finally:
            sys.stderr = real_stderr

        # Deal with special options that will lead to an early, successful exit.
        if opts.help:
            msg = ''.join((
                'U',
                ap.format_help()[1:],
                CON.newline,
                CLI.post_epilog,
            ))
            self.wrapup(CON.exit_ok, msg)
            return None
        elif opts.version:
            msg = f'{CON.app_name} v{__version__}'
            self.wrapup(CON.exit_ok, msg)
            return None

        # Validate the options related to input sources and structures.
        self.validate_sources_structures(opts)
        if self.done:
            return None
        else:
            return opts

    def create_arg_parser(self):
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
        return ap

    def validate_sources_structures(self, opts):
        # Define the checks:
        # - Exactly one source for input paths.
        # - Zero or one option specifying an input structure.
        checks = (
            (CLI.sources.keys(), False),
            (CLI.structures.keys(), True),
        )

        # Run the checks.
        for opt_names, zero_ok in checks:
            # N of sources or structures used.
            n = len(tuple(
                nm for nm in opt_names
                if getattr(opts, nm, None)
            ))

            # If there is a problem, first set the problem msg.
            if n == 0 and not zero_ok:
                msg = PF.opts_require_one
            elif n > 1:
                msg = PF.opts_mutex
            else:
                msg = None
                continue

            # And then register the problem message.
            choices = ', '.join(
                ('' if nm == CLI.sources.paths else '--') + nm
                for nm in opt_names
            )
            msg = f'{msg}: {choices}'
            self.wrapup(CON.exit_fail, msg)
            return

    def get_structure(self):
        gen = (s for s in STRUCTURES.keys() if getattr(self.opts, s, None))
        return next(gen, None)

    @property
    def log_data(self):
        d = dict(
            version = __version__,
            current_directory = str(Path.cwd()),
            opts = vars(self.opts),
        )
        d.update(**self.plan.as_dict)
        return d

    @property
    def log_file_path(self):
        home = Path.home()
        subdir = '.' + CON.app_name
        now = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
        return Path.home() / subdir / (now + '.json')

