import argparse
import json
import subprocess
import sys
import traceback

from datetime import datetime
from io import StringIO
from pathlib import Path
from textwrap import dedent
from short_con import constants

from .plan import RenamingPlan
from .problems import Problem, CONTROLS
from .version import __version__

from .utils import (
    MvsError,
    CON,
    MSG_FORMATS as MF,
    STRUCTURES,
    positive_int,
    read_from_clipboard,
    read_from_file,
)

####
# Entry point.
####

def main(args = None, **kws):
    args = sys.argv[1:] if args is None else args
    cli = CliRenamer(args, **kws)
    cli.run()
    sys.exit(cli.exit_code)

####
# A class to do the work of main() in way amenable to convenient testing.
####

class CliRenamer:

    ####
    # Initializer.
    ####

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

        # Attributes set during do_prepare():
        # - Command-line arguments and options.
        # - File path inputs from the user.
        # - The RenamingPlan instance.
        self.opts = None
        self.inputs = None
        self.plan = None

        # Status tracking:
        # - The exit_code attribute governs the self.done property
        # - The other attributes ensure each run() sub-step executes only once.
        self.exit_code = None
        self.has_prepared = False
        self.has_renamed = False

    ####
    # The top-level run() method and its immediate sub-steps.
    ####

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
        if self.done: # pragma: no cover
            return

        # Initialize the RenamingPlan.
        try:
            self.plan = RenamingPlan(
                inputs = self.inputs,
                rename_code = opts.rename,
                structure = self.get_structure_from_opts(),
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
        except MvsError as e:
            self.wrapup(CON.exit_fail, e.msg)
            return
        except Exception as e: # pragma: no cover
            self.wrapup_with_tb(MF.plan_creation_failed)
            return

        # Prepare the RenamingPlan and halt if it failed.
        plan.prepare()
        if plan.failed:
            msg = self.listing_msg(
                MF.prepare_failed_cli,
                plan.uncontrolled_problems,
            )
            self.wrapup(CON.exit_fail, msg)
            return

        # Print the renaming listing.
        listing = self.listing_msg(MF.paths_to_be_renamed, plan.rps)
        self.paginate(listing)

        # Stop if dryrun mode.
        if opts.dryrun:
            self.wrapup(CON.exit_ok, MF.no_action_msg)
            return

        # User confirmation.
        if not opts.yes:
            msg = self.msg_with_counts(MF.confirm_prompt, plan.rps)
            if not self.get_confirmation(msg, expected = CON.yes):
                self.wrapup(CON.exit_ok, MF.no_action_msg)
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
            self.wrapup(CON.exit_ok, MF.paths_renamed_msg)
        except Exception as e: # pragma: no cover
            self.wrapup_with_tb(MF.renaming_raised)

    ####
    # Helpers to finish or cut-short the run() sub-steps.
    ####

    @property
    def done(self):
        return self.exit_code is not None

    def wrapup(self, code, msg):
        # Helper for do_prepare() and do_rename().
        # Writes a newline-terminated message and sets exit_code.
        fh = self.stdout if code == CON.exit_ok else self.stderr
        msg = msg if msg.endswith(CON.newline) else msg + CON.newline
        fh.write(msg)
        self.exit_code = code

    def wrapup_with_tb(self, fmt):
        # Called in a raised-exception context.
        # Takes a message format and builds a wrapup() message
        # by adding the traceback.
        tb = traceback.format_exc()
        msg = fmt.format(tb)
        self.wrapup(CON.exit_fail, msg)

    ####
    # Command-line argument handling.
    ####

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
            if msg.startswith('usage:'):
                msg = 'U' + msg[1:]
            self.wrapup(CON.exit_fail, msg)
            return None
        finally:
            sys.stderr = real_stderr

        # Deal with special options that will lead to an early, successful exit.
        if opts.help:
            # Capitalize the initial "Usage" and add the post_epilog text.
            msg = ''.join((
                'U',
                ap.format_help()[1:],
                CON.newline,
                CLI.post_epilog,
            ))
            self.wrapup(CON.exit_ok, msg)
            return None
        elif opts.version:
            self.wrapup(CON.exit_ok, MF.cli_version_msg)
            return None

        # Validate the options related to input sources and structures.
        self.validate_sources_structures(opts)
        if self.done:
            return None
        else:
            return opts

    def create_arg_parser(self):
        # Define parser.
        ap = argparse.ArgumentParser(
            prog = CON.app_name,
            description = CLI.description,
            add_help = False,
        )
        # Add arguments, in argument-groups.
        # The presense of CLI.group in the configuration dict (oc)
        # signals the start of each new argument-group.
        arg_group = None
        for oc in CLI.opts_config:
            kws = dict(oc)
            if CLI.group in kws:
                arg_group = ap.add_argument_group(kws.pop(CLI.group))
            xs = kws.pop(CLI.names).split()
            arg_group.add_argument(*xs, **kws)
        # Return parser.
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
                msg = MF.opts_require_one
            elif n > 1:
                msg = MF.opts_mutex
            else:
                msg = None
                continue

            # And then wrapup with the problem message.
            choices = CON.comma_join.join(
                ('' if nm == CLI.sources.paths else CON.dash) + nm
                for nm in opt_names
            )
            msg = f'{msg}: {choices}'
            self.wrapup(CON.exit_fail, msg)
            return

    ####
    # Input path collection.
    ####

    def collect_input_paths(self):
        # Gets the input path text from the source.
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
            except Exception as e: # pragma: no cover
                self.wrapup_with_tb(MF.path_collection_failed)
                return None
            paths = text.split(CON.newline)
        return tuple(path.strip() for path in paths)

    ####
    # Logging.
    ####

    def write_to_json_file(self, path, d):
        try:
            Path(path).parent.mkdir(exist_ok = True)
            with open(path, 'w') as fh:
                json.dump(d, self.logfh or fh, indent = 4)
        except Exception as e: # pragma: no cover
            self.wrapup_with_tb(MF.log_writing_failed)

    @property
    def log_data(self):
        # Returns dict of logging data:
        # - Top-level CliRenamer info.
        # - Plus information from the RenamingPlan.
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
        subdir = CON.period + CON.app_name
        now = datetime.now().strftime(CON.datetime_fmt)
        return Path.home() / subdir / (now + CON.logfile_ext)

    ####
    # Listings and pagination.
    ####

    def msg_with_counts(self, fmt, xs):
        # Takes a message format and a sequence of items.
        # Returns a message followed by two counts in parentheses:
        # - N items
        # - N items listed, based on opts.limit
        n = len(xs)
        lim = n if self.opts.limit is None else self.opts.limit
        counts = f' (total {n}, listed {lim})'
        return fmt.format(counts)

    def listing_msg(self, fmt, xs):
        # Takes a message format and a sequence of items.
        # Returns a message-with-counts followed by a potentially-limited
        # listing of those items.
        msg = self.msg_with_counts(fmt, xs)
        items = CON.newline.join(x.formatted for x in xs[0:self.opts.limit])
        return f'{msg}\n{items}'

    def paginate(self, text):
        # Takes some text and either send it to the
        # configured pager or writes it to self.stdout.
        if self.opts.pager:
            p = subprocess.Popen(
                self.opts.pager,
                stdin = subprocess.PIPE,
                shell = True,
            )
            p.stdin.write(text.encode(CON.encoding))
            p.communicate()
        else:
            self.stdout.write(text)

    ####
    # Other.
    ####

    def get_confirmation(self, prompt, expected = 'y'):
        # Gets comfirmation from the command-line user.
        msg = prompt + f' [{expected}]? '
        self.stdout.write(msg)
        reply = self.stdin.readline().lower().strip()
        return reply == expected

    def get_structure_from_opts(self):
        # Determines the RenamingPlan.structure to use, based on opts.
        for s in STRUCTURES.keys():
            if getattr(self.opts, s, None):
                return s
        return None

####
# Configuration for command-line argument parsing.
####

class CLI:

    # Important option names or groups of options.

    paths = 'paths'
    sources = constants('Sources', ('paths', 'stdin', 'file', 'clipboard'))
    structures = constants('Structures', ('rename',) + STRUCTURES.keys())

    # Program help text: description and explanatory text.

    description = dedent('''
        Renames or moves files in bulk, via user-supplied Python
        code or a data source mapping old paths to new paths.
    ''')

    post_epilog = dedent('''
        The user-supplied renaming and filtering code has access to the
        original file path as a str [variable: o], its pathlib.Path
        representation [variable: p], the current sequence value [variable:
        seq], the RenamingPlan instance [variable: plan], some utility methods
        via than plan [plan.strip_prefix], and some Python libraries or classes
        [re, Path]. The functions should explicitly return a value: for
        renaming code, the desired new path, either as a str or a Path; for
        filtering code, any true value to retain the original path or any false
        value to reject it. The code should omit indentation on its first line,
        but must provide it for subsequent lines. For reference, here are some
        useful Path components in a renaming context: p.parent, p.name, p.stem,
        p.suffix.

        Before any renaming occurs, each pair of original and new paths is
        checked for common types of problems. By default, if any occur, the
        renaming plan is halted and no paths are renamed. The problems and
        their short names are as follows:

            equal     | Original path and new path are the same.
            missing   | Original path does not exist.
            existing  | New path already exists.
            colliding | Two or more new paths are the same.
            parent    | Parent directory of new path does not exist.

        Users can configure various problem controls to address such issues.
        That allows the renaming plan to proceed in spite of the problems,
        either by skipping offending items, taking remedial action, or simply
        forging ahead in spite of the consequences. The --create control
        applies only to a single type of problem (parent), the --clobber
        control can apply to two (existing, colliding), and the --skip control
        can apply to any or all. Here are some examples to illustrate usage:

            --skip equal         | Skip items with 'equal' problem.
            --skip equal missing | Skip items with 'equal' or 'missing' problems.
            --skip all           | Skip items with any type of problem.
            --clobber all        | Rename in spite of 'existing' and 'colliding' problems.
            --create parent      | Create missing parent before renaming.
            --create             | Same thing, more compactly.
    ''').lstrip()

    # Argument configuration for argparse.

    names = 'names'
    group = 'group'

    opts_config = (

        #
        # Input path sources.
        #
        {
            group: 'Input path sources',
            names: 'paths',
            'nargs': '*',
            'metavar': 'PATH',
            'help': 'Input paths via arguments',
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
        {
            names: '--clipboard',
            'action': 'store_true',
            'help': 'Input paths via the clipboard',
        },

        #
        # Options defining the structure of the input path data.
        #
        {
            group: 'Input path structures',
            names: '--flat',
            'action': 'store_true',
            'help': 'Input paths as a list: original paths, then equal number of new paths [default]',
        },
        {
            names: '--paragraphs',
            'action': 'store_true',
            'help': 'Input paths in paragraphs: original paths, blank line, new paths',
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

        #
        # User code for renaming and filtering.
        #
        {
            group: 'User code',
            names: '--rename -r',
            'metavar': 'CODE',
            'help': 'Code to convert original path to new path [implies inputs are just original paths]',
        },
        {
            names: '--filter',
            'metavar': 'CODE',
            'help': 'Code to filter input paths',
        },
        {
            names: '--indent',
            'type': positive_int,
            'metavar': 'N',
            'default': 4,
            'help': 'Number of spaces for indentation in user-supplied code [default: 4]',
        },
        {
            names: '--seq',
            'metavar': 'N',
            'type': positive_int,
            'default': 1,
            'help': 'Sequence start value [default: 1]',
        },
        {
            names: '--step',
            'metavar': 'N',
            'type': positive_int,
            'default': 1,
            'help': 'Sequence step value [default: 1]',
        },

        #
        # Renaming behaviors.
        #
        {
            group: 'Renaming behaviors',
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
            names: '--nolog',
            'action': 'store_true',
            'help': 'Suppress logging',
        },

        #
        # Listing/pagination.
        #
        {
            group: 'Listings',
            names: '--pager',
            'metavar': 'CMD',
            'default': CON.default_pager_cmd,
            'help': (
                'Command string for paginating listings [default: '
                f'`{CON.default_pager_cmd}`; empty string to disable]'
            ),
        },
        {
            names: '--limit',
            'metavar': 'N',
            'type': positive_int,
            'help': 'Upper limit on the number of items to display in listings [default: none]',
        },

        #
        # Failure control.
        #
        {
            group: 'Problem control',
            names: '--skip',
            'choices': CON.all_tup + Problem.names_for(CONTROLS.skip),
            'nargs': '+',
            'metavar': 'PROB',
            'help': 'Skip items with the named problems',
        },
        {
            names: '--clobber',
            'choices': CON.all_tup + Problem.names_for(CONTROLS.clobber),
            'nargs': '+',
            'metavar': 'PROB',
            'help': 'Rename anyway, in spite of named overwriting problems',
        },
        {
            names: '--create',
            'choices': Problem.names_for(CONTROLS.create),
            'nargs': '?',
            'metavar': 'PROB',
            'help': 'Fix missing parent problem before renaming',
        },

        #
        # Program information.
        #
        {
            group: 'Program information',
            names: '--help -h',
            'action': 'store_true',
            'help': 'Display this help message and exit',
        },
        {
            names: '--version',
            'action': 'store_true',
            'help': 'Display the version number and exit',
        },

    )

