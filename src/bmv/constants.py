from textwrap import dedent
from short_con import constants, cons

from .data_objects import(
    RpFilterFailure,
    RpRenameFailure,
    RpEqualFailure,
    RpMissingFailure,
    RpMissingParentFailure,
    RpExistsFailure,
    RpCollsionFailure,
)

class CON:
    app_name = 'bmv'
    newline = '\n'
    tab = '\t'
    underscore = '_'
    hyphen = '-'
    dash = hyphen + hyphen
    exit_ok = 0
    exit_fail = 1
    renamer_name = 'do_rename'
    filterer_name = 'do_filter'
    encoding = 'utf-8'
    no_action_msg = '\nNo action taken.'
    paths_renamed_msg = '\nPaths renamed.'
    default_pager_cmd = 'less'
    listing_batch_size = 10

    user_code_fmt = dedent('''
        def {func_name}(o, p, seq, plan):
        {indent}{user_code}
    ''').lstrip()

FAIL = cons('Fails',
    orig_missing = 'Original path does not exist',
    new_exists = 'New path exists',
    new_parent_missing = 'Parent directory of new path does not exist',
    orig_new_same = 'Original path and new path are the same',
    new_collision = 'New path collides with another new path',
    no_input_paths = 'No input paths',
    no_paths = 'No paths to be renamed',
    no_paths_after_processing = 'All paths were filtered out by failure control during processing',
    parsing_no_structures = 'No input structures given',
    parsing_row = 'The --rows option expects rows with exactly two cells: {row!r}',
    parsing_paragraphs = 'The --paragraphs option expects exactly two paragraphs',
    parsing_inequality = 'Got an unequal number of original paths and new paths',
    opts_require_one = 'One of these options is required',
    opts_mutex = 'No more than one of these options should be used',
    prepare_failed = 'RenamingPlan cannot rename paths because failures occurred during preparation',
    rename_done_already = 'RenamingPlan cannot rename paths because renaming has already been executed',
    conflicting_controls = 'Conflicting controls specified for a failure type: {} and {}',
    filter_code_invalid = 'Error in user-supplied filtering code: {} [original path: {}]',
    rename_code_invalid = 'Error in user-supplied renaming code: {} [original path: {}]',
    rename_code_bad_return = 'Invalid type from user-supplied renaming code: {} [original path: {}]',
    prepare_failed_cli = 'Renaming preparation resulted in failures:{}.\n',
    renaming_raised = '\nRenaming raised an error; some paths might have been renamed; traceback follows:\n\n{}',
)

# Failure control mechanisms.
CONTROLS = constants('Controls', (
    'skip',
    'keep',
    'create',
    'clobber',
))

# Mapping from the user-facing failure control names to their:
# (1) failure-control mechanisms and (2) Failure type.
#
#   skip   : The affected RenamePair will be skipped.
#   keep   : The affected RenamePair will be kept [rather than filtered out].
#   create : The missing path will be created [parent of RenamePair.new].
#   clobber: The affected path will be clobbered [existing or colliding RenamePair.new].
#
CONTROLLABLES = cons('Controllables',
    skip_failed_filter    = (CONTROLS.skip, RpFilterFailure),
    skip_failed_rename    = (CONTROLS.skip, RpRenameFailure),
    skip_equal            = (CONTROLS.skip, RpEqualFailure),
    skip_missing          = (CONTROLS.skip, RpMissingFailure),
    skip_missing_parent   = (CONTROLS.skip, RpMissingParentFailure),
    skip_existing_new     = (CONTROLS.skip, RpExistsFailure),
    skip_colliding_new    = (CONTROLS.skip, RpCollsionFailure),
    clobber_existing_new  = (CONTROLS.clobber, RpExistsFailure),
    clobber_colliding_new = (CONTROLS.clobber, RpCollsionFailure),
    keep_failed_filter    = (CONTROLS.keep, RpFilterFailure),
    create_missing_parent = (CONTROLS.create, RpMissingParentFailure),
 )

# Helper for argparse configuration to check for positive integers.
def positive_int(x):
    if x.isdigit():
        x = int(x)
        if x >= 1:
            return x
    raise ValueError

# Structures for input paths data.
#
# - paragraphs: Unix-style paragraphs:        old paths, blank line, new paths.
# - flat:       Just an even number of lines: old paths, then new paths [blank lines ignored].
# - pairs:      Alternating pairs of lines:   old, new, etc.
# - rows:       Tab-delimited rows:           old, tab, new.
#
STRUCTURES = constants('Structures', (
    'paragraphs',
    'flat',
    'pairs',
    'rows',
))

class CLI:
    # Command-line argument configuration.

    # Important option names or groups of options.
    paths = 'paths'
    sources = constants('Sources', ('paths', 'stdin', 'file', 'clipboard'))
    structures = constants('Structures', ('rename',) + STRUCTURES.keys())

    # Program help text: description and epilog.
    description = '''
        Renames or moves files in bulk, via user-supplied Python
        code or a data source mapping old paths to new paths.
    '''
    epilog = '''
        The user-supplied renaming and filtering code has access to the
        original file path as a str [variable: o], its pathlib.Path
        representation [variable: p], the current sequence value [variable:
        seq], some Python libraries or classes [re, Path], and some utility
        functions [strip_prefix]. The functions should explicitly return a
        value: for renaming code, the desired new path, either as a str or a
        Path; for filtering code, any true value to retain the original path or
        any false value to reject it. The code should omit indentation on its
        first line, but must provide it for subsequent lines. For reference,
        some useful Path components: p.parent, p.name, p.stem, p.suffix.
    '''

    # Argument configuration for argparse.
    names = 'names'
    group = 'group'
    opts_config = (

        # Input path sources.
        {
            group: 'Input path sources',
            names: 'paths',
            'nargs': '*',
            'metavar': 'PATH',
            'help': 'Input file paths',
        },
        {
            names: '--clipboard',
            'action': 'store_true',
            'help': 'Input paths via the clipboard',
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

        # Options defining the structure of the input path data.
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

        # User code for renaming and filtering.
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
            'help': 'Number of spaces for indentation in user-supplied code',
        },

        # Renaming behaviors.
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

        # Listing/pagination.
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

        # Sequence numbers.
        {
            group: 'Sequence numbers',
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

        # Failure control.
        {
            group: 'Failure control',
            names: '--skip-equal',
            'action': 'store_true',
            'help': 'If original path equals new, skip rename',
        },
        {
            names: '--skip-missing',
            'action': 'store_true',
            'help': 'If original path does not exist, skip rename',
        },
        {
            names: '--skip-missing-parent',
            'action': 'store_true',
            'help': 'If parent of new path does not exist, skip rename',
        },
        {
            names: '--create-missing-parent',
            'action': 'store_true',
            'help': 'If parent of new path does not exist, create parent before renaming',
        },
        {
            names: '--skip-existing-new',
            'action': 'store_true',
            'help': 'If new path already exists, skip rename',
        },
        {
            names: '--clobber-existing-new',
            'action': 'store_true',
            'help': 'If new path already exists, overwrite during renaming',
        },
        {
            names: '--skip-colliding-new',
            'action': 'store_true',
            'help': 'If new paths collide, skip renames',
        },
        {
            names: '--clobber-colliding-new',
            'action': 'store_true',
            'help': 'If new paths collide, overwrite during renaming',
        },
        {
            names: '--skip-failed-rename',
            'action': 'store_true',
            'help': 'If user renaming code fails when handling path, skip rename',
        },
        {
            names: '--skip-failed-filter',
            'action': 'store_true',
            'help': 'If user filtering code fails when handling path, skip rename',
        },
        {
            names: '--keep-failed-filter',
            'action': 'store_true',
            'help': 'If user filtering code fails when handling path, retain path',
        },

        # Program information.
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

