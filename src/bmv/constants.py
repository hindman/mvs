from textwrap import dedent
from short_con import constants, cons

from .problems import Problem, CONTROLS

class CON:
    app_name = 'bmv'
    all = 'all'
    all_tup = (all,)
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

    post_epilog = dedent('''
        Before any renaming occurs, each pair of original and new paths is checked
        for common types of problems. By default, if any occur, the renaming plan
        is halted and no paths are renamed. The problems and their short names are
        as follows:

            equal     | Original path and new path are the same.
            missing   | Original path does not exist.
            existing  | New path already exists.
            colliding | Two or more new paths are the same.
            parent    | Parent directory of new path does not exist.

        Users can configure various problem controls to address such issues. That
        allows the renaming plan to proceed in spite of the problems, either by
        skipping offending items, taking remedial action, or simply forging ahead
        in spite of the consequences. As shown in the usage documentation above,
        the --create control applies only to a single type of problem, the
        --clobber control can apply to multiple, and the --skip control can apply
        to any or all. Here are some examples to illustrate usage:

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

        # Failure control.
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

