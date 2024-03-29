### Basic functionality

    Defaults:
        - Never clobber existing files.
        - Log all changes to ~/.bmv/log/
        - Fail fast.
        - Take OLD names first via ARGV, else via STDIN.
        - Rename only if NEW name differs from OLD name.
        - Print only summary metadata as YAML.

    Input sources:
        stdin
        ARGV

    Input structures:
        --concatenated      # ORIG names, then NEW names
        --pairs

    Tranformations:
        --rename CODE
        - support filename components: path, directory, file_name, stem, ext

    Options and modes:
        --dryrun         # Also support: --dry and --dry-run
        --confirm


### Important options

    Options and modes:
        --clobber yes|no|ask
        --make_dirs
        --backup EXT|N|CODE
        --copy
        --link SOFT|HARD

### Project

    README: bare bones
    Gemspec
    Travis CI

### Tranformations: sequences and scriptlets

    Tranformations:

        - sequence numbers: n1, n2, n3
            --n1 START
            --n1 START,STOP             # Cycle when hitting STOP.
            --n1 START,STOP,SKIP

        - Implement tranformation recipes as scriptlets, some of which will be
          supplied by bmv and some via a user scriptlet directory.

        --remove_common PREFIX|SUFFIX

        --case LOWER|UPPER|CAMEL
        --replace STR1 STR2 N

        --trim
        --whitespace X    # All whitespace to single X


### More input sources and structures

    Input sources:
        --rows
        --delimiter X
        --input FILE
        --clipboard
        --input_glob GLOB    # Mainly for Windows.

    Input structures:
        --null               # null delim rather than newline
        --sort               # sort names
        --reverse            # reverse names

    Input filters
        --file_only
        --dirs_only
        --filter CODE        # Retain input item if code returns true.


### Preferences

    Options and modes:
        ~/.bmv/options.yml


### Project

    README
    Release Gem
    Announce: Stackoverflow, etc


### Undo mode and log management

    Options and modes:
        --undo N            # Undo previous renaming.

        --list              # List prior renamings.
        --log_dir
        --prune_logs N      # Keep N most recent renaming logs.
        --no_log


### Editor and mv modes

    Options and modes:

        --editor            # Open renamings in text file.
        --mv                # Behave like mv (with logging, etc).


### File attribute modes

    Options and modes:
        --chmod MODE
        --access_time TIME
        --modfy_time TIME
        --create_time TIME


### Output options

    Options and modes:

        --dryrun_style BASH|TAB|PARA|YAML|JSON|ORIG|NEW
        --verbose

