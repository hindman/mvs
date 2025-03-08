
## mvs: Because one mv is rarely enough

#### Motivation

Renaming a bunch of files and directories can be tedious, error-prone work.
Command-line tools to perform such tasks are numerous. Perhaps the most classic
example was the Perl [rename][perl_rename] script, which has been available or
installable on most Unix-inspired operating systems since the early 1990s.

The core idea of `rename` was excellent. The user supplied a snippet of Perl
code as a command-line argument, followed by the original paths. Each original
path was pumped through the code snippet to generate the corresponding new
path. Because Perl was designed to make it easy to manipulate strings with very
little code, users could efficiently rename paths directly on the command line.
Even if you hardly knew Perl but at least understood how to operate its compact
regular-expression substitution syntax, you could become quite adept at bulk
path renaming.

```bash
$ rename 's/foo/bar/' *
```

Unfortunately, the script was a chainsaw – undeniably useful, but able to
inflict devastation after a single false move. As a result, I rarely used
`rename` directly for my bulk renaming needs, which were extensive on several
projects I worked on. Instead, I wrote my own Perl script to do the job. Its
operation was roughly the same, but it included precautions to help me avoid
disastrous mistakes. The most important were checking that the new paths did
not collide with existing paths on the file system and including an inspection
and confirmation step by default.

The `mvs` library is an updated and enhanced version of those ideas, but
implemented in a language I use regularly (Python) rather than one in which
I have become rusty (Perl).

#### The mvs executable

The primary use case envisioned for the library is its executable. In broad
terms, there are two ways to perform bulk renaming with the `mvs` command: (1)
the user provides original file paths and a snippet of Python code to perform
the original-to-new computation, or (2) the user provides both original paths
and new paths directly.

Either way, before any renaming occurs, mvs checks for common problems that
might occur in bulk renaming scenarios, provides an informative listing of the
proposed renamings grouping them into meaningful categories based on those
checks, and waits for user confirmation before attempting any renamings. In
addition, the script logs detailed information about the renamings to support
the user in the event that they later regret what they have done.

The script provides various command-line options to customize its behavior,
supports user preferences, and provides detailed documentation on policy,
process, listings, user-supplied code, problem checking, configuration,
logging, and caveats.

#### Installation and examples

Install the library in the usual way.

```bash
$ pip install mvs
```

Get usage help and detailed documentation.

```bash
$ mvs --help
$ mvs --details
```

A simple example:

```bash
$ mvs a b --rename 'return f"{o}.new"'
```

#### Programmatic usage

The mvs package also supports bulk renaming via a programmatic API. This can be
done by creating a `RenamingPlan` instance and then calling its
`rename_paths()` method. Initialization parameters and their defaults are as
follows.

```python
from mvs import RenamingPlan

plan = RenamingPlan(
    # Sequence of paths and their structure.
    inputs,
    structure = 'flat',

    # User-supplied renaming and filtering code (str or callable).
    # See mvs --details for additional information.
    rename_code = None,
    filter_code = None,

    # Other parameters related to user-supplied code.
    indent = 4,
    seq_start = 1,
    seq_step = 1,

    # Additional rigor in the face of problems.
    # See mvs --details problems.
    skip = None,
    strict = None,
)

plan.rename_paths()
```

If you do not want to rename paths immediately but do want to prepare
everything for renaming, including performing the checks for problems, you can
use the library in a more deliberative fashion: first prepare; then check the
information provided by the plan; if desired, proceed with renaming; and in the
event of unexpected failure, get information about which item led to the
exception.

```python
# The library's supported imports.
from mvs import RenamingPlan, MvsError, __version__

# Configure plan.
plan = RenamingPlan(...)

# Prepare for renaming.
plan.prepare()

# All relevant information about the plan and its renamings.
print(plan.as_dict)

# Whether preparation failed.
print(plan.failed)

# The renamings organized into four groups:
# - filtered out by user code;
# - excluded, due to unresolvable problems;
# - skipped, due to resolvable problems configured by user an ineligible;
# - active renamings.
print(plan.filtered)
print(plan.excluded)
print(plan.skipped)
print(plan.active)

# Try to rename.
try:
    plan.rename_paths()
except Exception as e:
    # The index of the active Renaming that was being handled
    # when the exception occurred. Renamings before that index were
    # renamed succesfully; renamings after it were not attempted.
    i = plan.tracking_index
    print(i)

    # Two ways to see the offending renaming.
    print(plan.tracking_rn)
    print(plan.active[i])

    # Renamings that were performed.
    print(plan.active[:i])

    # Renamings that were not attempted.
    print(plan.active[i + 1:])
```

--------

[perl_rename]: https://metacpan.org/dist/File-Rename/view/source/rename

