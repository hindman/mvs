from textwrap import dedent
from short_con import constants, cons

class CON:
    app_name = 'bmv'
    newline = '\n'
    tab = '\t'
    exit_ok = 0
    exit_fail = 1
    renamer_name = 'do_rename'
    filterer_name = 'do_filter'
    encoding = 'utf-8'
    no_action_msg = '\nNo action taken.'
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
    no_paths = 'No paths to be renamed',
    parsing_opts = 'Unexpected options during parsing: no paths or structures given',
    parsing_row = 'The --rows option expects rows with exactly two cells: {row!r}',
    parsing_paragraphs = 'The --paragraphs option expects exactly two paragraphs',
    parsing_inequality = 'Got an unequal number of original paths and new paths',
    opts_require_one = 'One of these options is required',
    opts_mutex = 'No more than one of these options should be used',
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
        # Sources for input paths.
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
            names: '--rename -r',
            'metavar': 'CODE',
            'help': 'Code to convert original path to new path',
        },
        {
            names: '--paragraphs',
            'action': 'store_true',
            'help': 'Input paths in paragraphs: original paths, blank line, new paths',
        },
        {
            names: '--flat',
            'action': 'store_true',
            'help': 'Input paths in non-delimited paragraphs: original paths, then new',
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
        # Pagination options.
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
        # Other options.
        {
            group: 'Other',
            names: '--help -h',
            'action': 'store_true',
            'help': 'Display this help message and exit',
        },
        {
            names: '--version',
            'action': 'store_true',
            'help': 'Display the version number and exit',
        },
        {
            names: '--skip-equal',
            'action': 'store_true',
            'help': 'Skip renamings with equal paths rather than reporting as errors',
        },
        {
            names: '--dryrun -d',
            'action': 'store_true',
            'help': 'List renamings without performing them',
        },
        {
            names: '--nolog',
            'action': 'store_true',
            'help': 'Suppress logging',
        },
        {
            names: '--yes',
            'action': 'store_true',
            'help': 'Rename files without a user confirmation step',
        },
        {
            names: '--indent',
            'type': positive_int,
            'metavar': 'N',
            'default': 4,
            'help': 'Number of spaces for indentation in user-supplied code',
        },
        {
            names: '--filter',
            'metavar': 'CODE',
            'help': 'Code to filter input paths',
        },
    )

