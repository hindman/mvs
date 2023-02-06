
## mvs: Because one mv is rarely enough

#### Motivation

Renaming a bunch of files and directories can be tedious, error-prone work.
Command-line tools to perform such tasks are numerous. Perhaps the most classic
example was the Perl [rename][perl_rename] script, which has been available or
installable on most Unix-inspired operating systems since the early 1990s.

The core idea of the classic `rename` was inspired. The user supplied a snippet
of Perl code as a command-line argument, followed by the original paths. Each
original path was pumped through the code snippet and the code's resulting
value was used as the new path. Because Perl had been designed to make it easy
to manipulte strings with very little code, users could efficiently rename
paths in a variety of ways directly on the command line. Even if you knew very
little Perl but at least undersood how to operate is regular-expression
substitution machinery, you could be quite adept at bulk path renaming.

    rename 's/foo/bar/' *.txt

Unfortunately, the script was a bit like a chainsaw -- undeniably useful, but
also able to inflict devasting damage with a single false move. So I used my
own variant of the script, which wrapped a few safety features around it.
Moreover, I stopped writing code in Perl in the early 2000s and must skills
grew rusty.

...

```python
...
```

--------

[pypi_optopus]: https://pypi.org/project/optopus/
[perl_rename]: https://metacpan.org/dist/File-Rename/view/source/rename

