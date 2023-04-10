import argparse
import json
import os
import subprocess
import sys
import traceback

from datetime import datetime
from io import StringIO
from pathlib import Path
from textwrap import dedent
from short_con import constants

from .plan import RenamingPlan
from .version import __version__

from .utils import (
    CON,
    LISTING_CHOICES,
    LISTING_FORMATS,
    MSG_FORMATS as MF,
    MvsError,
    OptConfig,
    Problem,
    STRUCTURES,
    StrictMode,
    edit_text,
    hyphens_to_underscores,
    indented,
    positive_int,
    read_from_clipboard,
    read_from_file,
    validated_choices,
    wrap_text,
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

    LOG_TYPE = constants('LogType', (
        'plan',
        'tracking',
    ))

    ####
    # Initializer.
    ####

    def __init__(self,
                 args,
                 stdout = sys.stdout,
                 stderr = sys.stderr,
                 stdin = sys.stdin,
                 logfh = None):

        # Attributes received as arguments.
        self.args = args
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
        # - Datetime when first log file was written.
        # - Attributes ensure each run() sub-step executes only once.
        self.exit_code = None
        self.logged_at = None
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
                skip = opts.skip,
                strict = opts.strict,
            )
            plan = self.plan
        except MvsError as e: # pragma: no cover
            self.wrapup(CON.exit_fail, e.msg)
            return
        except Exception as e: # pragma: no cover
            self.wrapup_with_tb(MF.plan_creation_failed)
            return

        # Prepare the RenamingPlan, log plan information, and halt if it failed.
        plan.prepare()
        self.write_log_file(self.LOG_TYPE.plan)

        # Print the renaming listing.
        self.paginate(self.renaming_listing())

        if plan.failed:
            self.wrapup(CON.exit_fail, MF.no_action_msg)
            return

        # Stop if dryrun mode.
        if opts.dryrun:
            self.wrapup(CON.exit_ok, MF.no_action_msg)
            return

        # User confirmation.
        if not opts.yes:
            if not self.get_confirmation(MF.confirm_prompt, expected = CON.yes):
                self.wrapup(CON.exit_ok, MF.no_action_msg)

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
            msg = MF.renaming_raised.format(self.plan.tracking_index)
            self.wrapup_with_tb(msg)
        finally:
            self.write_log_file(self.LOG_TYPE.tracking)

    ####
    # Helpers to finish or cut-short the run() sub-steps.
    ####

    @property
    def done(self):
        return self.exit_code is not None

    def wrapup(self, code, msg):
        # Helper for do_prepare() and do_rename().
        # Writes a newline-terminated message and sets exit_code.
        # The latter is use in those methods to short-circuit.
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

        # Load user preferences.
        prefs = self.load_preferences()
        if self.done:
            return None

        # Merge the preferences into the opts.
        opts = self.merge_opts_prefs(opts, prefs)
        if self.done:
            return None

        # Deal with special options that will lead to an early, successful exit.
        if opts.help:
            # Capitalize the initial "Usage".
            msg = 'U' + ap.format_help()[1:]
            self.wrapup(CON.exit_ok, msg)
            return None
        elif opts.details:
            msg = self.wrapped_post_eplilog(ap)
            self.wrapup(CON.exit_ok, msg)
            return None
        elif opts.version:
            self.wrapup(CON.exit_ok, MF.cli_version_msg)
            return None

        # Validate the options related to input sources and structures.
        self.validate_sources_structures(opts)
        if self.done:
            return None

        # Normalize opts.list (argparse already valided it).
        opts.list = validated_choices(opts.list, LISTING_CHOICES)

        # Done.
        return opts

    def load_preferences(self):
        # Return empty if there is no user-preferences file.
        path = self.user_prefs_path
        if path.is_file():
            path = str(path)
        else:
            return {}

        # Try to read the preferences and ensure
        # that the JSON represents a dict.
        try:
            with open(path) as fh:
                prefs = dict(json.load(fh))
        except Exception as e:
            msg = MF.prefs_reading_failed.format(path)
            self.wrapup_with_tb(msg)
            return None

        # Return dict with normalized keys.
        return {
            hyphens_to_underscores(k) : v
            for k, v in prefs.items()
        }

    def merge_opts_prefs(self, opts, prefs):
        # Confirm that the prefs keys are valid.
        invalid = set(prefs) - set(CLI.opt_configs)
        if invalid:
            invalid_str = CON.comma_space.join(invalid)
            msg = MF.invalid_pref_keys.format(invalid_str)
            self.wrapup(CON.exit_fail, msg)
            return None

        # Check data types of the pref values.
        for name, val in prefs.items():
            oc = CLI.opt_configs[name]
            expected_type = oc.check_value(val)
            if expected_type:
                msg = MF.invalid_pref_val.format(oc.name, expected_type, val)
                self.wrapup(CON.exit_fail, msg)
                return None

        # Attributes that either don't require merging.
        special = {'disable'}

        # Merge preferences into opts. If the current opts attribute
        # is unset and if the preference was not disabled on the
        # command line via --disable, apply the preference to opts.
        for name, val in prefs.items():
            if not (name in special or name in opts.disable):
                current = getattr(opts, name)
                if current in CLI.unset_opt_vals:
                    setattr(opts, name, val)

        # Apply the real_default values to any attributes that were
        # not set either in user-prefs or on the command line.
        for oc in CLI.opt_configs.values():
            rd = oc.real_default
            if rd is not None:
                current = getattr(opts, oc.name)
                if current in CLI.unset_opt_vals:
                    setattr(opts, oc.name, rd)

        # Return.
        return opts

    @property
    def user_prefs_path(self):
        return self.app_directory / CON.prefs_file_name

    def create_arg_parser(self):
        # Define parser.
        ap = argparse.ArgumentParser(
            prog = CON.app_name,
            description = CLI.description,
            add_help = False,
        )

        # Add arguments, in argument groups.
        arg_group = None
        for oc in CLI.opt_configs.values():
            if oc.group:
                arg_group = ap.add_argument_group(oc.group)
            arg_group.add_argument(*oc.names, **oc.params)

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

    def wrapped_post_eplilog(self, ap):
        # Use the argparse help text to compute the desired width.
        lines = ap.format_help().split(CON.newline)
        width = max(len(line) for line in lines)

        # Split the post-epilog into paragraphs.
        # Wrap the paragraph unless it is a heading or indented.
        paras = []
        for p in CLI.post_epilog.split(CON.para_break):
            if not p.startswith('  ') and not p.endswith('----'):
                p = wrap_text(p, width)
            paras.append(p)

        # Join the paragraphs back into a block of text.
        return CON.para_break.join(paras)

    ####
    # Input path collection.
    ####

    def collect_input_paths(self):
        # Gets the input path text from the source.
        # Returns a tuple of stripped lines.
        opts = self.opts

        # Read the input path text from the initial source.
        if opts.paths:
            text = CON.newline.join(opts.paths)
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

        # If the user wants to use an editor, run the text through that process.
        if opts.edit:
            if not opts.editor:
                self.wrapup(CON.exit_fail, MF.no_editor)
                return None
            try:
                text = edit_text(opts.editor, text)
            except Exception as e:
                self.wrapup_with_tb(MF.edit_failed_unexpected)
                return None

        # Split, strip, return.
        paths = text.split(CON.newline)
        return tuple(path.strip() for path in paths)

    ####
    # Logging.
    ####

    def write_log_file(self, log_type):
        # Bail if we aren't logging. Otherwise, prepare the log
        # file path and logging data. On the first logging call
        # we also set self.logged_at (the datetime to used
        # in both logging calls).
        if self.opts.nolog: # pragma: no cover
            return

        # Otherwise, prepare the log file path and logging data.
        # On the first logging call we also set self.logged_at,
        # which is the datetime to used in both logging calls.
        self.logged_at = self.logged_at or datetime.now()
        path = self.log_file_path(log_type)
        d = self.log_data(log_type)

        # Try to write the logging data.
        try:
            json_text = json.dumps(d, indent = 4)
            if self.logfh:
                self.logfh.write(json_text)
            Path(path).parent.mkdir(exist_ok = True)
            with open(path, 'w') as fh:
                fh.write(json_text)
        except Exception as e: # pragma: no cover
            self.wrapup_with_tb(MF.log_writing_failed)

    @property
    def app_directory(self):
        app_dir = os.environ.get(CON.app_dir_env_var)
        if app_dir:
            return Path(app_dir)
        else:
            return Path.home() / (CON.period + CON.app_name)

    def log_file_path(self, log_type):
        now = self.logged_at.strftime(CON.datetime_fmt)
        return self.app_directory / f'{now}-{log_type}.{CON.logfile_ext}'

    def log_data(self, log_type):
        # Returns a dict of logging data containing either:
        # (1) the RenamingPlan tracking index or
        # (2) the top-level CliRenamer info plus the RenamingPlan info.
        if log_type == self.LOG_TYPE.tracking:
            return dict(tracking_index = self.plan.tracking_index)
        else:
            d = dict(
                version = __version__,
                current_directory = str(Path.cwd()),
                opts = vars(self.opts),
            )
            d.update(**self.plan.as_dict)
            return d

    ####
    # Listings and pagination.
    ####

    def renaming_listing(self):
        # A renaming listing shown to the user before asking for
        # confirmation to proceed with renaming.
        sections = tuple(
            (fmt, getattr(self.plan, k))
            for k, fmt in LISTING_FORMATS
        )
        return self.para_join(
            self.failure_listing(),
            self.summary_listing(),
            self.section_listing(sections),
        )

    def para_join(self, *msgs):
        sep = CON.newline + CON.newline
        return sep.join(
            m.rstrip()
            for m in msgs
            if m
        )

    def failure_listing(self):
        # A renaming listing shown if the renaming plan
        # was halted during preparation.
        f = self.plan.failure
        if f:
            return MF.plan_failed.format(f.msg)
        else:
            return ''

    def summary_listing(self):
        # Returns a message summarizing a renaming as a table of tallies,
        # but only if the plan would fail under strict=all.
        p = self.plan
        if p.passes_strict_all:
            return ''
        else:
            return MF.summary_table.format(
                p.n_initial,
                len(p.filtered),
                len(p.skipped),
                len(p.excluded),
                len(p.active),
                len(p.parent),
                len(p.exists),
                len(p.collides),
                len(p.ok),
            )

    def section_listing(self, sections):
        # Takes data defining the sections of a renaming or failure listing.
        # Returns sections as a message for any non-empty sections.
        return CON.newline.join(
            self.listing_msg(fmt, items)
            for fmt, items in sections
            if items
        )

    def listing_msg(self, fmt, items):
        # Takes a message format and a sequence of items
        # having a formatted @property (in practice, the items
        # are Failure or Renaming instances).
        #
        # Attaches a tally of the items to the message.
        #
        # Returns that message followed by a listing of those items.
        # The listing might be limited in size.
        n = len(items)
        lim = n if self.opts.limit is None else self.opts.limit
        tally = f' (total {n})'
        msg = fmt.format(tally)
        items = CON.newline.join(
            indented(x.formatted)
            for x in items[0:self.opts.limit]
        )
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
            self.stdout.write(text + CON.newline)

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
        Renames file and directory paths in bulk, via user-supplied
        Python code or a data source mapping old paths to new paths.
        No renaming occurs until all of the proposed changes have
        been checked for common types of problems.
    ''')

    post_epilog = dedent('''
        User-supplied code
        ------------------

        The user-supplied renaming and filtering code receives the following
        variables as function arguments:

          o     Original path.
          p     Original path, as a pathlib.Path instance.
          seq   Current sequence value.
          plan  RenamingPlan instance.

        The code also has access to these Python libraries or classes:

          re    Python re library.
          Path  Python pathlib.Path class.

        The RenamingPlan provides the strip_prefix() method, which takes a str
        (presumably the original path) and returns a new str with the common
        prefix (across all original paths) removed.

        User-supplied code should explictly return a value, as follows:

          Renaming   New path, as a str or Path.
          Filtering  True to retain original path, False to reject

        The code text does not require indentation for its first line,
        but does require it for any subsequent lines.

        For reference, here are some useful Path attributes and methods in a
        renaming context:

          p         Path('/parent/dir/foo-bar.fubb')
          p.parent  Path('/parent/dir')

          p.name    'foo-bar.fubb'
          p.stem    'foo-bar'
          p.suffix  '.fubb'
          p.parts   ('/', 'parent', 'dir', 'foo-bar.fubb')

          p.exists()   bool
          p.is_file()  "
          p.is_dir()   "

          p.with_name(X)    New Path having name X.
          p.with_stem(X)    "               stem X.
          p.with_suffix(X)  "               suffix X.

        Problem control
        ---------------

        Before any renamings occur, each is checked for common types of
        problems. By default, if any occur, the renaming plan is halted and no
        paths are renamed. The problems and their short names are as follows:

          equal      Original path and new path are the same.
          missing    Original path does not exist.
          existing   New path already exists.
          colliding  Two or more new paths are the same.
          parent     Parent directory of new path does not exist.

        Users can configure various problem controls to address such issues.
        That allows the renaming plan to proceed in spite of the problems,
        either by skipping offending items, taking remedial action (creating a
        missing parent for a new path), or simply forging ahead in spite of the
        consequences (clobbering).

        The controls and their applicable problems:

          skip     All of them.
          create   parent.
          clobber  existing, colliding.

        Examples:

          # Skipping items with specific problems.
          --skip equal
          --skip equal missing

          # Shortcut to control all applicable problems.
          --skip all
          --clobber all

          # Creating missing parents before renaming.
          --create parent
    ''').lstrip()

    # Values in the parsed opts indicating that the user did not
    # set the option on the command line. Used when merging
    # the user preferences into opts.
    unset_opt_vals = (False, None, [])

    # Text used in various OptConfig help texts.
    just_origs_msg = 'implies inputs are just original paths'

    # Argument configuration for argparse.
    opt_configs = (

        #
        # Input path sources.
        #
        OptConfig(
            group = 'Input path sources',
            names = 'paths',
            validator = OptConfig.list_of_str,
            nargs = '*',
            metavar = 'PATH',
            help = 'Input paths via arguments',
        ),
        OptConfig(
            names = '--stdin',
            validator = bool,
            action = 'store_true',
            help = 'Input paths via STDIN',
        ),
        OptConfig(
            names = '--file',
            validator = str,
            metavar = 'PATH',
            help = 'Input paths via a text file',
        ),
        OptConfig(
            names = '--clipboard',
            validator = bool,
            action = 'store_true',
            help = 'Input paths via the clipboard',
        ),

        #
        # Options defining the structure of the input path data.
        #
        OptConfig(
            group = 'Input path structures',
            names = '--flat',
            validator = bool,
            action = 'store_true',
            help = 'Input paths: original paths, then equal number of new paths [the default]',
        ),
        OptConfig(
            names = '--paragraphs',
            validator = bool,
            action = 'store_true',
            help = 'Input paths in paragraphs: original paths, blank line(s), new paths',
        ),
        OptConfig(
            names = '--pairs',
            validator = bool,
            action = 'store_true',
            help = 'Input paths in alternating lines: original, new, original, new, etc.',
        ),
        OptConfig(
            names = '--rows',
            validator = bool,
            action = 'store_true',
            help = 'Input paths in tab-delimited rows: original, tab, new',
        ),

        #
        # User code for renaming and filtering.
        #
        OptConfig(
            group = 'User code',
            names = '--rename -r',
            validator = str,
            metavar = 'CODE',
            help = f'Code to convert original path to new path [{just_origs_msg}]',
        ),
        OptConfig(
            names = '--filter',
            validator = str,
            metavar = 'CODE',
            help = 'Code to filter input paths',
        ),
        OptConfig(
            names = '--indent',
            validator = OptConfig.posint,
            real_default = 4,
            type = positive_int,
            metavar = 'N',
            default = None,
            help = 'Number of spaces for indentation in user-supplied code [default: 4]',
        ),
        OptConfig(
            names = '--seq',
            validator = OptConfig.posint,
            real_default = 1,
            metavar = 'N',
            type = positive_int,
            default = None,
            help = 'Sequence start value [default: 1]',
        ),
        OptConfig(
            names = '--step',
            validator = OptConfig.posint,
            real_default = 1,
            metavar = 'N',
            type = positive_int,
            default = None,
            help = 'Sequence step value [default: 1]',
        ),

        #
        # Renaming via editing.
        #
        OptConfig(
            group = 'Renaming via editing',
            names = '--edit',
            validator = bool,
            action = 'store_true',
            help = f'Create new paths via a text editor [{just_origs_msg}]',
        ),
        OptConfig(
            names = '--editor',
            validator = str,
            real_default = CON.default_editor_cmd,
            metavar = 'CMD',
            help = (
                'Command string for editor used by --edit [default: '
                f'`{CON.default_editor_cmd}`; empty string to disable]'
            ),
        ),

        #
        # Renaming behaviors.
        #
        OptConfig(
            group = 'Renaming behaviors',
            names = '--dryrun -d',
            validator = bool,
            action = 'store_true',
            help = 'List renamings without performing them',
        ),
        OptConfig(
            names = '--yes',
            validator = bool,
            action = 'store_true',
            help = 'Rename files without a user confirmation step',
        ),
        OptConfig(
            names = '--nolog',
            validator = bool,
            action = 'store_true',
            help = 'Suppress logging',
        ),

        #
        # Listing/pagination.
        #
        OptConfig(
            group = 'Listings',
            names = '--pager',
            validator = str,
            real_default = CON.default_pager_cmd,
            metavar = 'CMD',
            help = (
                'Command string for paginating listings [default: '
                f'`{CON.default_pager_cmd}`; empty string to disable]'
            ),
        ),
        OptConfig(
            names = '--list',
            metavar = 'NAME',
            validator = OptConfig.list_of_str,
            nargs = '+',
            choices = LISTING_CHOICES,
            help = 'Specify the sections to include in listings',
        ),
        OptConfig(
            names = '--limit',
            validator = OptConfig.posint,
            metavar = 'N',
            type = positive_int,
            help = 'Upper limit on the number of items to display in listings [default: none]',
        ),

        #
        # Problem handling and other configuration.
        #
        OptConfig(
            group = 'Problem handling and other configuration',
            names = '--skip',
            metavar = 'PROB',
            validator = OptConfig.list_of_str,
            nargs = '+',
            choices = Problem.SKIP_CHOICES,
            help = 'Skip renamings having the named problems [see --details]',
        ),
        OptConfig(
            names = '--strict',
            metavar = 'PROB',
            validator = OptConfig.list_of_str,
            nargs = '+',
            choices = StrictMode.CHOICES,
            help = 'Halt renaming plan if any renamings have the named problems [see --details]',
        ),
        OptConfig(
            names = '--disable',
            validator = OptConfig.list_of_str,
            nargs = '+',
            metavar = 'FLAG',
            default = [],
            help = 'Disable flag options that were set true in user preferences',
        ),

        #
        # Program information.
        #
        OptConfig(
            group = 'Program information',
            names = '--help -h',
            validator = bool,
            action = 'store_true',
            help = 'Display this help message and exit',
        ),
        OptConfig(
            names = '--details',
            validator = bool,
            action = 'store_true',
            help = 'Display additional help details and exit',
        ),
        OptConfig(
            names = '--version',
            validator = bool,
            action = 'store_true',
            help = 'Display the version number and exit',
        ),

    )

    # Convert opt_configs from tuple to dict so that
    # we can look them up by name.
    opt_configs = {
        hyphens_to_underscores(oc.name) : oc
        for oc in opt_configs
    }

    # Set the choices parameter for the --disable option.
    opt_configs['disable'].params['choices'] = tuple(
        oc.name
        for oc in opt_configs.values()
        if oc.is_flag
    )

