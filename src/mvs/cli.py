import argparse
import json
import os
import subprocess
import sys
import traceback

from collections import defaultdict
from datetime import datetime
from io import StringIO
from pathlib import Path
from short_con import cons
from textwrap import dedent

from .constants import CON, STRUCTURES
from .optconfig import OptConfig, positive_int
from .plan import RenamingPlan
from .problems import Problem, StrictMode, build_summary_table
from .version import __version__

from .messages import (
    LISTING_CHOICES,
    LISTING_FORMATS,
    LISTING_CATEGORIES,
    DETAILS_SECTIONS,
    MSG_FORMATS as MF,
)

from .utils import (
    MvsError,
    edit_text,
    hyphens_to_underscores,
    indented,
    para_join,
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

    LOG_TYPE = cons('plan', 'tracking')

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
        # - Attributes to ensure each run() sub-step executes only once.
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

        # Prepare the RenamingPlan, log plan information.
        # Halt if logging failed.
        plan.prepare()
        self.write_log_file(self.LOG_TYPE.plan)
        if self.done:
            return

        # Print the renaming listing.
        self.paginate(self.renaming_listing())

        # Return if plan failed.
        if plan.failed:
            self.wrapup(CON.exit_fail, MF.no_action)
            return

        # Return if dryrun mode.
        if opts.dryrun:
            self.wrapup(CON.exit_ok, MF.no_action)
            return

        # User confirmation.
        if not opts.yes:
            if not self.get_confirmation(MF.confirm_prompt, expected = CON.yes):
                self.wrapup(CON.exit_ok, MF.no_action)
                return

    def do_rename(self):
        # Don't execute more than once.
        if self.has_renamed:
            return
        else:
            self.has_renamed = True

        # Rename paths.
        try:
            self.plan.rename_paths()
            self.wrapup(CON.exit_ok, MF.paths_renamed)
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
        elif opts.details is not None:
            msg = self.wrapped_details(ap, opts.details)
            self.wrapup(CON.exit_ok, msg)
            return None
        elif opts.version:
            self.wrapup(CON.exit_ok, MF.cli_version)
            return None

        # Validate the options related to input sources and structures.
        if opts.origs and not opts.rename:
            self.wrapup(CON.exit_fail, MF.opts_origs_rename)
            return None
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

        # Attributes that don't require merging.
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
            (STRUCTURES.keys(), True),
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

    def wrapped_details(self, ap, sections):
        # If needed, adjust which sections the user wants.
        if not sections:
            sections = [DETAILS_SECTIONS.sections]
        elif CON.all in sections:
            sections = DETAILS_SECTIONS.values()

        # Use the argparse help text to compute the desired width.
        lines = ap.format_help().split(CON.newline)
        width = max(len(line) for line in lines)

        # For the desired sections, split the text into paragraphs.
        # Wrap each paragraph unless it is a heading or indented.
        paras = []
        for s in sections:
            for p in CLI.details[s].split(CON.para_break):
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
                    text = self.read_from_stdin()
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

    def read_from_stdin(self):
        # Reads from self.stdin and returns its content.
        #
        # If the file handle is sys.stdin we close and reopen it,
        # because user confirmation will need to read self.stdin.
        #
        # The latter behavior is not easy to test. For now,
        # we rely on the tests/stdin-check script.
        blob = self.stdin.read()
        if self.stdin is sys.stdin: # pragma: no cover
            terminal = os.ctermid()
            self.stdin.close()
            self.stdin = open(terminal)
        return blob

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
            (LISTING_FORMATS[k], getattr(self.plan, k))
            for k in LISTING_CATEGORIES.keys()
        )
        return para_join(
            self.failure_listing(),
            self.summary_listing(),
            self.section_listing(sections),
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
        # Returns a message summarizing a renaming as a table of tallies.
        # The tallies are suppressed if all renamings are active and OK.
        p = self.plan
        N = len(p.active)
        if p.n_initial == N and N == len(p.ok):
            return ''

        # Intialize a dict of tallies with the top-level counts.
        tally = defaultdict(int)
        tally.update(
            total = p.n_initial,
            filtered = len(p.filtered),
            excluded = len(p.excluded),
            skipped = len(p.skipped),
            active = len(p.active),
            ok = len(p.ok),
        )

        # Add Problem details to the tally for excluded/skipped renamings.
        # Here the tally keys are based directly on the Problem SID.
        for rn in p.excluded + p.skipped:
            prob = rn.problem
            if prob:
                k = hyphens_to_underscores(prob.sid)
                tally[k] += 1

        # Do the same for active renamings.
        # Here the tally keys use Problem.name plus a prefix to
        # distinguish their keys from those in excluded/skipped.
        for rn in p.active:
            prob = rn.problem
            if prob:
                k = 'active_' + hyphens_to_underscores(prob.name)
                tally[k] += 1

        # Return the table text. This function will exclude detail
        # rows having a count of zero.
        return build_summary_table(tally)

    def section_listing(self, sections):
        # Takes data defining the sections of a renaming or failure listing.
        # Returns sections as a message for any non-empty sections.
        return CON.newline.join(
            self.listing_msg(fmt, items)
            for fmt, items in sections
            if items
        )

    def listing_msg(self, fmt, rns):
        # Takes a message format and a sequence of Renaming instances.
        #
        # Attaches a tally of the renamings to the message.
        #
        # Returns that message followed by a listing of those renamings.
        # The listing might be limited in size.
        n = len(rns)
        lim = n if self.opts.limit is None else self.opts.limit
        tally = f' (total {n})'
        msg = fmt.format(tally)
        rns_text = CON.newline.join(
            indented(rn.formatted)
            for rn in rns[0:self.opts.limit]
        )
        return f'{msg}\n{rns_text}'

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
# Help text: details
####

DEETS = {}

DEETS[DETAILS_SECTIONS.sections] = f'''

    Sections
    --------

    The detailed help is organized into sections. Supply one or more
    arguments with the --details option to see them.

        {DETAILS_SECTIONS.sections} | Sections
        {DETAILS_SECTIONS.policy}   | Policy
        {DETAILS_SECTIONS.process}  | Process
        {DETAILS_SECTIONS.listing}  | Listing
        {DETAILS_SECTIONS.code}     | User-supplied code
        {DETAILS_SECTIONS.problems} | Problems
        {DETAILS_SECTIONS.config}   | Configuration and logging
        {DETAILS_SECTIONS.caveats}  | Caveats

'''

DEETS[DETAILS_SECTIONS.policy] = '''

    Policy
    ------

    The philosophy or policy of the mvs script has four key principles.

    Reasonable caution. The script halts in the face of invalid input and
    it checks for a variety of problems typical in renaming scenarios. But
    it does not take pains to catch rare problems that can under complex or
    exotic scenarios.

    Informed consent. No renamings are executed without user confirmation.
    As part of the confirmation process renamings are listed in general
    categories (filtered, excluded, skipped, or active) along with
    information charactizing any problems revealed by the checks.

    Eager renaming, with guardrails. By default, mvs prefers to execute
    renamings. Specifically, that means the following: (1) even if some
    renamings have unresolvable problems, mvs will proceed with the others
    that do not; (2) even if some new paths lack an existing parent, mvs
    will create the needed parent directories; and (3) even is some new
    paths are already occupied, mvs will perform a clobber (delete current
    item at the path, then perform the original-to-new renaming). But mvs
    will not make heroic efforts to fulfill renaming prequisities, and it
    does not support renamings or clobberings for path types other than
    directory or regular file.

    Rigor via configuration. The user can suppress that renaming eagerness
    via command line arguments and a configuration file. Renamings having
    resolvable problems can be automatically skipped. Or mvs can be
    configured to halt before starting renaming if problems occur -- either
    any problems or those of specific kinds.

'''

DEETS[DETAILS_SECTIONS.process] = '''

    Process
    -------

    The process used by the mvs script can be described has have five
    general phases.

    Collect inputs. The script parses command-line arguments, reads the
    user preferences configuration file, and merges the two (command-line
    settings override configuration). Then in collects input paths and
    allows the user to edit them (if --edit). Failures or invalid input
    during this phase will cause mvs to halt.

    Prepare the renaming plan. The script initializes a RenamingPlan instance,
    which parses input paths into pairs of original and new paths, runs
    user-supplied code to filter out paths, and then runs user-supplied code to
    create or modify new paths.

    Check for problems. Each proposed renaming is checked for the
    following: are the original and new paths identical; is the original
    path unique across all original paths; does the original path exist; is
    the original path a supported file type (directory or regular file);
    does the new path exist already and, if so, what is its file type; does
    the parent of the new path exist; and does the new path collide
    another new path and, if so, what is its file type?

    Listing and logging. The script prints a listing of all proposed
    renamings and logs all RenamingPlan details. The script halts
    if the plan failed or if the user specified --dryrun.

    Confirmation. The user is prompted to confirm than renaming
    should proceed (unless --yes).

    Renaming. The script attempts to perform the active renamings. During
    that process it updates the tracking log file.

'''

DEETS[DETAILS_SECTIONS.listing] = '''

    Listing
    -------

    Before asking the user for confirmation to proceed, mvs prints a
    listing that organizes the proposed renamings into four broad groups:

        filtered | by user code
        excluded | due to unresolvable problems
        skipped  | due to resolvable problems configured by user as ineligible
        active   | awaiting confirmation

    Active renamings are further classified according to the type of
    problem they have, if any.

        parent   | parent of new path does not exist
        exists   | new path exists
        collides | new path collides with another new path
        ok       | no problems

    By default, the listing includes all applicable groups. The user can
    restrict the listing to one or more specific groups: filtered,
    excluded, skipped, parent, exists, collides, or ok.

'''

DEETS[DETAILS_SECTIONS.code] = '''

    User-supplied code
    ------------------

    User code should return a value, as follows:

        renaming  | new path, as a str or Path
        filtering | True to retain original path, False to reject

    User code has access to the following variables:

        o    | original path (str)
        n    | new path (str or None)
        po   | original path (pathlib.Path)
        pn   | new path (pathlib.Path or None)
        seq  | current sequence value
        r    | current Renaming instance
        plan | renamingPlan instance

    User code has access to these libraries or classes:

        re   | Python re library.
        Path | Python pathlib.Path class.

    Helpers available via the RenamingPlan instance:

        plan.strip_prefix(ORIG_PATH): returns str with common prefix
        (across all original paths) removed.

    Indentation required in user-supplied code:

        First line  | no indent needed
        Other lines | indent required

    Path attributes and methods handy in a renaming context:

        po                | Path('/parent/dir/foo-bar.fubb')
        po.parent         | Path('/parent/dir')
        po.name           | 'foo-bar.fubb'
        po.stem           | 'foo-bar'
        po.suffix         | '.fubb'
        po.parts          | ('/', 'parent', 'dir', 'foo-bar.fubb')
        po.exists()       | bool
        po.is_file()      | bool
        po.is_dir()       | bool
        po.with_name(X)   | Path with name X
        po.with_stem(X)   | Path with stem X
        po.with_suffix(X) | Path with suffix X

'''

DEETS[DETAILS_SECTIONS.problems] = '''

    Problems
    --------

    During a renaming scenario there can be failures and problems.

    Failures. These are not specific to a single renaming and/or have no
    resolution. Most relate to bad inputs. Failures halt the renaming plan
    early before any renamings occur.

    Problems. These are specific to one renaming. Some of them are
    unresolvable: for example, if the original path does not exist the
    renaming is impossible. Other problems are resolvable and they come in
    two general categories: (1) if a new path implies a parent directory
    that does not exist yet, mvs can create the directory before attempting
    the renaming; and (2) if a new path already exists, mvs can delete the
    curent item at that path before renaming. Problems have a general name
    and an optional variety to further classify them.

    Unresolvable problems:

        Name      | Variety | Description
        -----------------------------------------------------------------------------------
        noop      | equal   | ORIG and NEW are equal
        noop      | same    | ORIG and NEW are functionally the same
        noop      | recase  | Renaming just a case-change, but file system agrees with NEW
        missing   | .       | ORIG does not exist
        duplicate | .       | ORIG is the same as another ORIG
        type      | .       | ORIG is neither a regular file nor directory
        code      | filter  | Error from user-supplied filtering code
        code      | rename  | Error or invalid return from user-supplied renaming code
        exists    | other   | NEW exists and is neither regular file nor directory

    Resolvable problems:

        Name     | Variety | Description
        -----------------------------------------------------------------------------------
        exists   | .       | NEW exists
        exists   | diff    | NEW exists and differs with ORIG in type
        exists   | full    | NEW exists and is a non-empty directory
        collides | .       | NEW collides with another NEW
        collides | diff    | NEW collides with another NEW, and they differ in type
        collides | full    | NEW collides with another NEW, and it is a non-empty directory
        parent   | .       | Parent directory of NEW does not exist

    Skipping resolvable problems. The user can configure mvs to skip
    renamings having specific types of resolvable problems. This is done
    with the --skip option, which takes one or more problem NAME or
    NAME-VARIETY values. A few examples:

        --skip exists collides
        --skip exists-full collides-full
        --skip all

    Halting the renaming plan in the face of resolvable problems. Via the
    --strict option, the user can configure mvs to halt the renaming plan
    if certain types of problems are found. A few examples:

        # Halt if any renamings were excluced due to unresolvable problems.
        --strict excluded

        # Halt if any renamings had resolvable problems of various types.
        --strict parent
        --strict parent exists collides

        # Maximum strictness.
        --strict all
        --strict excluded parent exists collides

'''

DEETS[DETAILS_SECTIONS.config] = '''

    Configuration and logging
    -------------------------

    The mvs directory. This directory holds the configuration file for user
    preferences along with all mvs log files. By default that directory is
    $HOME/.mvs but the user can specify a different location via the
    MVS_APP_DIR environment variable.

    User preferences file. By default the file is located at
    $HOME/.mvs/config.json and its structure directly mimics the
    command-line options: keys are the same as the command-line options,
    and values are the desired settings. An example:

        {
            "nolog": true,
            "indent": 2,
            "editor": "emacs"
        }

    Logging. By default, each renaming scenario produces two log files, one
    containing all details of the RenamingPlan (DATETIME-plan.json) and the
    other indicating which original-to-new renaming was active in the event
    that that attempt to rename the paths failed unexpectedly
    (DATETIME-tracking.json). The intent of the log files is to support the
    user by providing as much information as possible in cases where the
    user messed up (renamings that they later regret) or where some
    unexpected error occurred during an attempted renaming. In the face of
    such errors, no other renamings are attempted. The user can use the two
    log files to determine all details of the attempted renaming and which
    specific renaming led to the unexpected error.

'''

DEETS[DETAILS_SECTIONS.caveats] = '''

    Caveats
    -------

    Interactions among renamings. Complex interactions among renamings are not
    guarded against with any rigor. The mvs library checks the renaming plan
    against the current file system: it does not check each renaming against
    the future file system after some renamings in the plan have occurred. The
    general advice is to be sensible and incremental in your work. If you have
    a lot of renamings to perform involving complex interactions, break the
    work down into smaller steps that are easier for you (and the mvs code) to
    reason about.

    Case-insensitive file systems. The mvs code is tested on case-sensitive and
    case-preserving operating systems, but not on case-insensitive systems. In
    that context, regular renamings will probably work fine. However, to give
    one example, case-change-only renamings will not be interpreted as problems
    by the mvs checks even though, when attempted, such a renaming would fail
    on a case-insensitive system.

    Renaming operates only on the leaf node of a path. The mvs code renames
    only the leaf of a file path, not the leaf and its parent. When checking a
    proposed renaming, mvs asks whether the parent of its new path exists. If
    yes, then the renaming does not need to concern itself with the parent
    since the renaming affects only the leaf node. If no, mvs will create the
    missing parent (at least by default). What mvs will not do is rename an
    existing parent while also renaming the leaf portions of paths within that
    parent. That restriction is reasonable: such a parent directory might
    contain other material and mvs was not instructed modify it.

    Sequences numbers can have gaps under some scenarios. Such numbers are
    relevant only when new paths are created or modified by user-supplied code.
    The sequence numbers supplied to that code are guaranteed to be gapless.
    However, if the user's renaming code fails or returns an invalid value, the
    renaming will be marked as having an unresolvable problem and thus skipped.
    Similarly, after new paths are calculated, the renaming checks might find
    other unresolvable problems, leading to more skipped renamings. If the user
    provides confirmation to proceed with the renaming plan in that kind of
    situation, the sequence numbers among the actually renamed paths would have
    gaps. The advice given above to be sensible applies here: if you care about
    gapless sequences, do not confirm a renaming plan containing unresolvable
    problems.

    The --pager and --editor commands use a shell. This is done so that the
    values supplied for those options can themselves contain spaces, arguments,
    and options. Do not supply values for --pager and --editor that would fail
    under subprocess.run(COMMAND, shell = True).

    Renamings across files systems. Renaming is implemented with pathlib, which
    depends on os.rename() and os.replace(). According to the documenation for
    those operations, renaming across file systems can fail. More generally,
    the mvs libary is not tested under such scenarios.

'''

####
# Configuration for command-line argument parsing.
####

class CLI:

    # Important option names or groups of options.

    paths = 'paths'
    sources = cons('paths', 'stdin', 'file', 'clipboard')

    # Program help text: description and detailed help sections.

    description = dedent('''

        Renames file and directory paths in bulk, via user-supplied Python code
        or a data source mapping old paths to new paths. By default, no
        renaming occurs until: (1) the renamings have been checked for common
        types of problems; (2) the user reviews the renamings and other summary
        information; and (3) the user provides confirmation to proceed.

    ''')

    details = {
        k : dedent(v).strip()
        for k, v in DEETS.items()
    }

    # Values in the parsed opts indicating that the user did not
    # set the option on the command line. Used when merging
    # the user preferences into opts.
    unset_opt_vals = (False, None, [])

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
            metavar = 'PATHS',
            help = 'Input paths via arguments',
        ),
        OptConfig(
            names = '--stdin',
            validator = bool,
            action = 'store_true',
            help = 'Input paths via STDIN',
        ),
        OptConfig(
            names = '--clipboard',
            validator = bool,
            action = 'store_true',
            help = 'Input paths via the clipboard',
        ),
        OptConfig(
            names = '--file',
            validator = str,
            metavar = 'PATH',
            help = 'Input paths via a text file',
        ),

        #
        # Options defining the structure of the input path data.
        #
        OptConfig(
            group = 'Input path structures',
            names = '--flat',
            validator = bool,
            action = 'store_true',
            help = 'Original paths, then an equal number of new paths [the default]',
        ),
        OptConfig(
            names = '--paragraphs',
            validator = bool,
            action = 'store_true',
            help = 'Original paths, blank line(s), then new paths',
        ),
        OptConfig(
            names = '--pairs',
            validator = bool,
            action = 'store_true',
            help = 'Alternating lines: original, new, original, new, etc.',
        ),
        OptConfig(
            names = '--rows',
            validator = bool,
            action = 'store_true',
            help = 'Tab-delimited rows: original, tab, new',
        ),
        OptConfig(
            names = '--origs',
            validator = bool,
            action = 'store_true',
            help = 'Original paths only [requires --rename]',
        ),

        #
        # User code for renaming and filtering.
        #
        OptConfig(
            group = 'User code',
            names = '--filter',
            validator = str,
            metavar = 'CODE',
            help = 'Code to filter input paths',
        ),
        OptConfig(
            names = '--rename -r',
            validator = str,
            metavar = 'CODE',
            help = f'Code to create or modify new paths',
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
            help = f'Modify input paths via a text editor',
        ),
        OptConfig(
            names = '--editor',
            validator = str,
            real_default = CON.default_editor_cmd,
            metavar = 'CMD',
            help = f'Command string for editor [default: `{CON.default_editor_cmd}`]',
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
                f'`{CON.default_pager_cmd}`; empty to disable]'
            ),
        ),
        OptConfig(
            names = '--list',
            metavar = 'NAME',
            validator = OptConfig.list_of_str,
            nargs = '+',
            choices = LISTING_CHOICES,
            help = 'Specify the sections to include in listings [see --details]',
        ),
        OptConfig(
            names = '--limit',
            validator = OptConfig.posint,
            metavar = 'N',
            type = positive_int,
            help = 'Upper limit on number of items to display in listings [default: none]',
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
            nargs = '*',
            metavar = 'S',
            choices = (CON.all, *DETAILS_SECTIONS.values()),
            help = 'Display one or more sections from help details and exit',
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

