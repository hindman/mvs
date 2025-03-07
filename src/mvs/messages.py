from short_con import cons

from .constants import CON
from .version import __version__

####
# Renaming categories using in listings.
####

LISTING_FORMATS = cons(
    filtered = '# Renamings: filtered out by user code{}:\n',
    excluded = '# Renamings: excluded due to unresolvable problems{}:\n',
    skipped  = '# Renamings: skipped by user due to problems{}:\n',
    parent   = '# Active renamings: will create new parent{}:\n',
    exists   = '# Active renamings: will clobber existing path{}:\n',
    collides = '# Active renamings: will collide with another new path{}:\n',
    ok       = '# Active renamings: with no problems{}:\n',
)

LISTING_CATEGORIES = cons(
    'filtered',
    'excluded',
    'skipped',
    'parent',
    'exists',
    'collides',
    'ok',
)

PARENT_LISTING_CATEGORIES = cons(
    'filtered',
    'excluded',
    'skipped',
    'active',
)

LISTING_CHOICES = (CON.all, *LISTING_CATEGORIES.keys())

####
# Sections in the detailed help text.
####

DETAILS_SECTIONS = cons(
    'sections',
    'policy',
    'process',
    'listing',
    'code',
    'problems',
    'config',
)

####
# Messages.
####

MSG_FORMATS = MF = cons(
    # MvsError instances in RenamingPlan.
    rename_done_already    = 'RenamingPlan cannot rename paths because renaming has already been executed',
    prepare_failed         = 'RenamingPlan cannot rename paths because failures occurred during preparation',
    invalid_control        = 'Invalid problem control: {!r}',
    invalid_skip           = 'Invalid value for RenamingPlan.skip: {!r}',
    invalid_problem        = 'Invalid Problem name or variety: name={!r}, variety={!r}',
    invalid_strict         = 'Invalid value for RenamingPlan.strict: {!r}',
    conflicting_controls   = 'Conflicting controls for problem {!r}: {!r} and {!r}',
    invalid_controls       = 'Invalid value for RenamingPlan controls parameter',
    unrequested_clobber    = 'Renaming would cause unrequested clobbering to occur',
    unsupported_clobber    = 'Renaming would cause unsupported path type to be clobbered',
    # Error messages in CliRenamer.
    path_collection_failed = 'Collection of input paths failed.\n\n{}',
    plan_creation_failed   = 'Unexpected error during creation of renaming plan.\n\n{}',
    log_writing_failed     = 'Unexpected error during writing to log file.\n\n{}',
    prefs_reading_failed   = 'Unexpected error during reading of user preferences {!r}.\n\n{{}}',
    renaming_raised        = '\nRenaming raised an error at tracking_index={}. Traceback follows:\n\n{{}}',
    opts_require_one       = 'One of these options is required',
    opts_mutex             = 'No more than one of these options should be used',
    opts_origs_rename      = 'The --origs option requires --rename',
    invalid_pref_val       = 'User preferences: invalid value for {}: expected {}: got {!r}',
    invalid_pref_keys      = 'User preferences: invalid key(s): {}',
    no_editor              = 'The --edit option requires an --editor',
    editor_cmd_nonzero     = 'Editor process exited unsuccessfully: editor={!r}, path={!r}',
    edit_failed_unexpected = 'Editing failed unexpectedly. Traceback follows:\n\n{}',
    plan_failed            = 'Plan failed: {}',
    # Other messages in CliRenamer.
    confirm_prompt         = '\nRename paths',
    no_action              = '\nNo action taken.',
    paths_renamed          = '\nPaths renamed.',
    cli_version            = f'{CON.app_name} v{__version__}',
)

