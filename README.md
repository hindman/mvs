
## mvs: Because one mv is rarely enough

#### Motivation

Renaming a bunch of files and directories can be tedious, error-prone work.
Command-line tools to perform such tasks are numerous. Perhaps the most classic
example was the Perl [rename][perl_rename] script, which has been available or
installable on most Unix-inspired operating systems since the early 1990s.

The core idea of the `rename` script was excellent. The user supplied a snippet
of Perl code as a command-line argument, followed by the original paths. Each
original path was pumped through the code snippet to generate the corresponding
new path. Because Perl had been designed to make it easy to manipulte strings
with very little code, users could efficiently rename paths in a variety of
ways directly on the command line. Even if you knew very little Perl but at
least undersood how to operate its compact regular-expression substitution
syntax, you could be quite adept at bulk path renaming.

```bash
$ rename 's/foo/bar/' *.txt
```

Unfortunately, the script was a chainsaw -- undeniably useful, but able to
inflict devastation with a single false move. As a result, I rarely used
`rename` directly for my bulk-renaming needs, which were extensive on several
projects I worked on. Instead, I wrote my own Perl script to the job. Its
operation was roughly the same, but it included obvious checks to help me avoid
disastrous mistakes, most importantly checking that the new paths did not
collide with existing paths on the file system and including a user inspection
and confirmation step by default.

The `mvs` library is an updated and enhanced version of those ideas, but
implemented in a language I use regularly (Python) rather than one in which
I've become rusty (Perl).

#### The mvs executable

The primary use case envisioned for the library is its executable. In broad
terms, there are two ways to perform bulk-renaming with the `mvs` command: (1)
user provides original file paths and a snippet of Python code to perform the
original-to-new computation, or (2) user provides both original paths and new
paths directly.

Either way, before any renaming occurs, the following checks occur: are the
original paths different than their corresponding new paths; do all the
original paths exist; do any new paths already exist; do any new paths collide
with each other; and are the parent directories of any new paths missing? If
those checks look alright, the proposed renamings are listed for inspection by
the user. Renaming occurs after user confirmation.

The script provides command-line options to customize the command's behavior:

- Supply input paths in various ways: positional arguments, STDIN, a text data
  file, or the clipboard.

- Organize the original and new paths in various structures: a flat sequence,
  in Unix-style paragraphs, as alternating pairs of lines, or as delimited
  rows.

- Use a snippet of Python code to filter out original paths before renaming,
  which can be handy if you want to supply paths via a command-line glob
  pattern but you don't want to rename all of them.

- Specify in advance how the program should respond to any of the validation
  problems listed above: skip the item with the problem, rename in spite of the
  problem (even it that means overwriting other paths), or take remedial action
  (create a missing parent directory).

- Define a sequence number for use in the renaming code snippet.

- Execute in dryrun mode, which executes the command's renaming, filtering,
  checking, and listing behavior but does not rename anything.

#### Installation and examples

Install the library in the usual way.

```bash
$ pip install mvs
```

Get help and additional details regarding the options summarized above.

```bash
$ mvs --help
$ mvs --details
```

In general terms, the command has the following usage. Note that the default
structure is flat and that the `--rename` option is consisered structual
because in implies that the input path data consists solely of original paths.

```text
mvs SOURCE [STRUCTURE] [OTHER]

PATHS     : positionals
SOURCE    : PATHS | --stdin | --file PATH | --clipboard
STRUCTURE : --flat | --paragraphs | --pairs | --rows | --rename CODE
OTHER     : all other options
```

The different input structures can be illustrated with a simple renaming
scenario where we just want to add a file extension to the original paths. Note
that if the paths were supplied via a source other than positional arguments,
each path should be on its own line.

```bash
# The default: a flat sequence of paths.
$ mvs a b a.new b.new
$ mvs a b a.new b.new --flat

# Alternating pairs.
$ mvs a a.new b b.new --pairs

# Paragraphs delimited by one or more blank lines.
$ mvs a b '' a.new b.new --paragraphs
```

The same renaming scenario could also be performed via a code snippet. The code
snippet will be compiled into a function that receives the original path as the
local variable `o` and it should explicitly return the new path. See the
program's help text for additional details about user-supplied code.

```bash
$ mvs a b --rename 'return r"{o}.new"'
```

#### Library usage

The mvs package also supports bulk renaming via a programmatic API. The first
step is to configure a `RenamingPlan` (initialization parameters and their
defaults are shown below).

```python
from mvs import RenamingPlan

plan = RenamingPlan(
    # Sequence of paths and their structure (default: 'flat').
    inputs,
    structure = None,

    # User-supplied renaming and filtering code (str or callable).
    rename_code = None,
    filter_code = None,

    # Other details regarding user-supplied code.
    indent = 4,
    seq_start = 1,
    seq_step = 1,

    # Problem controls. For each control mechanism, supply the
    # names of the problems to be controlled via the mechanism,
    # either as a sequence or space-delimited str.
    # See mvs --details for the problem names.
    skip = None,
    clobber = None,
    create = None,
)

plan.rename_paths()
```

If you don't want to rename paths immediately but do want to prepare everything
for renaming, including performing the checks for problems, you use the library
in a more deliberative fashion: first prepare; then check the information
provided by the plan; if desired, proceed with renaming; and in the event of
unexpected failure, get information on which item failed.

```python
# The library's supported imports.
from mvs import RenamingPlan, MvsError, __version__

# Configure plan.
plan = RenamingPlan(...)

# Prepare for renaming.
plan.prepare()

# Information about the plan and its original-new path pairs.
print(plan.as_dict)

# Whether preparation failed due to problems.
print(plan.failed)
print(plan.uncontrolled_problems)

# Try to rename.
try:
    plan.rename_paths()
except Exception as e:
    # The index of the original-new pair that was being renamed
    # when the exception occurred. Pairs before that index were
    # renamed succesfully; pairs after it were not attempted.
    print(plan.tracking_index)

    # The offending original-new pair.
    print(plan.tracking_rp)
```

--------

[perl_rename]: https://metacpan.org/dist/File-Rename/view/source/rename

