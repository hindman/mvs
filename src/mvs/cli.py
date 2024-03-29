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
from .problems import Problem, CONTROLS
from .version import __version__

from .utils import (
    CON,
    MSG_FORMATS as MF,
    MvsError,
    PrefType,
    STRUCTURES,
    list_of_str,
    list_or_str,
    posint_pref,
    positive_int,
    read_from_clipboard,
    edit_text,
    read_from_file,
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
        self.write_log_file(self.LOG_TYPE.plan)

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
        else:
            return opts

    def load_preferences(self):
        # Return empty if there is no user-preferences file.
        path = self.user_prefs_path
        if not path.is_file():
            return {}

        # Try to read the preferences.
        try:
            with open(path) as fh:
                return json.load(fh)
        except Exception as e: # pragma: no cover
            msg = MF.prefs_reading_failed.format(str(path))
            self.wrapup_with_tb(msg)

    def merge_opts_prefs(self, opts, prefs):
        # Use the command-line options configuration data to
        # create a dict of PrefType instances.
        ptypes = tuple(
            self.oc_to_preftype(oc)
            for oc in CLI.opts_config
        )
        ptypes = {
            pt.name : pt
            for pt in ptypes
        }

        # Confirm that the prefs keys are valid.
        invalid = set(prefs) - set(ptypes)
        if invalid:
            invalid = CON.comma_space.join(invalid)
            msg = MF.invalid_pref_keys.format(invalid)
            self.wrapup(CON.exit_fail, msg)
            return None

        # Check data types of the prefs.
        for name, val in prefs.items():
            pt = ptypes[name]
            expected = pt.check_value(val)
            if expected:
                msg = MF.invalid_pref_val.format(pt.name, expected, val)
                self.wrapup(CON.exit_fail, msg)
                return None

        # Merge preferences into opts. If the current opts attribute is unset
        # and if the preference was not disabled via --disable, apply the
        # preference to opts.
        for name, val in prefs.items():
            if name not in opts.disable:
                current = getattr(opts, name)
                if current in CLI.unset_opt_vals:
                    setattr(opts, name, val)

        # Create a dict of the real_default values.
        rds = {
            parse_oc_name(oc) : oc[CLI.real_default]
            for oc in CLI.opts_config
            if CLI.real_default in oc
        }

        # Apply real defaults to any attributes that were
        # not set either in user-prefs or on the command line.
        for name, rd in rds.items():
            current = getattr(opts, name)
            if current in CLI.unset_opt_vals:
                setattr(opts, name, rd)

        # Boom.
        return opts

    def oc_to_preftype(self, oc):
        name = parse_oc_name(oc)
        valid = oc[CLI.dtype]
        return PrefType(name, valid)

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
        # Add arguments, in argument-groups.
        # The presense of CLI.group in the configuration dict (oc)
        # signals the start of each new argument-group.
        arg_group = None
        for oc in CLI.opts_config:
            kws = dict(oc)
            kws.pop(CLI.dtype)
            kws.pop(CLI.real_default, None)
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

def parse_oc_name(oc):
    return oc['names'].split()[0].lstrip(CON.hyphen)

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

        For reference, here are some useful Path components in a renaming
        context:

          p         Path('/parent/dir/foo-bar.fubb')
          p.parent  Path('/parent/dir')
          p.name    'foo-bar.fubb'
          p.step    'foo-bar'
          p.suffix  '.fubb'

        Problem control
        ---------------

        Before any renaming occurs, each pair of original and new paths is
        checked for common types of problems. By default, if any occur, the
        renaming plan is halted and no paths are renamed. The problems and
        their short names are as follows:

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

    # Important key names in opts_config.
    names = 'names'
    group = 'group'
    dtype = 'dtype'
    real_default = 'real_default'

    # Values in the parsed opts indicating that the user did not
    # set the option on the command line. Used when merging 
    # the user preferences into opts.
    unset_opt_vals = (False, None, [])

    just_origs_msg = 'implies inputs are just original paths'

    # Argument configuration for argparse.
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
            dtype: list_of_str,
        },
        {
            names: '--stdin',
            'action': 'store_true',
            'help': 'Input paths via STDIN',
            dtype: bool,
        },
        {
            names: '--file',
            'metavar': 'PATH',
            'help': 'Input paths via a text file',
            dtype: str,
        },
        {
            names: '--clipboard',
            'action': 'store_true',
            'help': 'Input paths via the clipboard',
            dtype: bool,
        },

        #
        # Options defining the structure of the input path data.
        #
        {
            group: 'Input path structures',
            names: '--flat',
            'action': 'store_true',
            'help': 'Input paths: original paths, then equal number of new paths [the default]',
            dtype: bool,
        },
        {
            names: '--paragraphs',
            'action': 'store_true',
            'help': 'Input paths in paragraphs: original paths, blank line(s), new paths',
            dtype: bool,
        },
        {
            names: '--pairs',
            'action': 'store_true',
            'help': 'Input paths in alternating lines: original, new, original, new, etc.',
            dtype: bool,
        },
        {
            names: '--rows',
            'action': 'store_true',
            'help': 'Input paths in tab-delimited rows: original, tab, new',
            dtype: bool,
        },

        #
        # User code for renaming and filtering.
        #
        {
            group: 'User code',
            names: '--rename -r',
            'metavar': 'CODE',
            'help': f'Code to convert original path to new path [{just_origs_msg}]',
            dtype: str,
        },
        {
            names: '--filter',
            'metavar': 'CODE',
            'help': 'Code to filter input paths',
            dtype: str,
        },
        {
            names: '--indent',
            'type': positive_int,
            'metavar': 'N',
            'default': None,
            real_default: 4,
            'help': 'Number of spaces for indentation in user-supplied code [default: 4]',
            dtype: posint_pref,
        },
        {
            names: '--seq',
            'metavar': 'N',
            'type': positive_int,
            'default': None,
            real_default: 1,
            'help': 'Sequence start value [default: 1]',
            dtype: posint_pref,
        },
        {
            names: '--step',
            'metavar': 'N',
            'type': positive_int,
            'default': None,
            real_default: 1,
            'help': 'Sequence step value [default: 1]',
            dtype: posint_pref,
        },

        #
        # Renaming via editing.
        #
        {
            group: 'Renaming via editing',
            names: '--edit',
            'action': 'store_true',
            'help': f'Create new paths via a text editor [{just_origs_msg}]',
            dtype: bool,
        },
        {
            names: '--editor',
            'metavar': 'CMD',
            'default': None,
            real_default: CON.default_editor_cmd,
            'help': f'Command string for editor used by --edit [default: {CON.default_editor_cmd}]',
            dtype: str,
        },

        #
        # Renaming behaviors.
        #
        {
            group: 'Renaming behaviors',
            names: '--dryrun -d',
            'action': 'store_true',
            'help': 'List renamings without performing them',
            dtype: bool,
        },
        {
            names: '--yes',
            'action': 'store_true',
            'help': 'Rename files without a user confirmation step',
            dtype: bool,
        },
        {
            names: '--nolog',
            'action': 'store_true',
            'help': 'Suppress logging',
            dtype: bool,
        },

        #
        # Listing/pagination.
        #
        {
            group: 'Listings',
            names: '--pager',
            'metavar': 'CMD',
            'default': None,
            real_default: CON.default_pager_cmd,
            'help': (
                'Command string for paginating listings [default: '
                f'`{CON.default_pager_cmd}`; empty string to disable]'
            ),
            dtype: str,
        },
        {
            names: '--limit',
            'metavar': 'N',
            'type': positive_int,
            'help': 'Upper limit on the number of items to display in listings [default: none]',
            dtype: posint_pref,
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
            dtype: list_or_str,
        },
        {
            names: '--clobber',
            'choices': CON.all_tup + Problem.names_for(CONTROLS.clobber),
            'nargs': '+',
            'metavar': 'PROB',
            'help': 'Rename anyway, in spite of named overwriting problems',
            dtype: list_or_str,
        },
        {
            names: '--create',
            'choices': CON.all_tup + Problem.names_for(CONTROLS.create),
            'nargs': '+',
            'metavar': 'PROB',
            'help': 'Fix missing parent problem before renaming',
            dtype: list_or_str,
        },

        #
        # Other.
        #
        {
            group: 'Other',
            names: '--disable',
            'nargs': '+',
            'metavar': 'FLAG',
            'default': [],
            'help': 'Disable flag options that were set true in user preferences',
            dtype: bool,
        },
        {
            names: '--help -h',
            'action': 'store_true',
            'help': 'Display this help message and exit',
            dtype: bool,
        },
        {
            names: '--details',
            'action': 'store_true',
            'help': 'Display additional help details and exit',
            dtype: bool,
        },
        {
            names: '--version',
            'action': 'store_true',
            'help': 'Display the version number and exit',
            dtype: bool,
        },

    )

    for oc in opts_config:
        if parse_oc_name(oc) == 'disable':
            oc['choices'] = tuple(
                parse_oc_name(oc)
                for oc in opts_config
                if oc.get('action') == 'store_true'
            )
            break

