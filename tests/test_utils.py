import pytest

# Import these directly from the package.
from mvs import RenamingPlan, MvsError, __version__

from mvs.utils import with_newline

def test_top_level_imports(tr):
    # Exercise the package's top-level importables.
    # Do something simple with each one.
    assert 'a' in RenamingPlan(inputs = ('a', 'b')).inputs
    assert MvsError('foo', x = 1).msg == 'foo'
    assert isinstance(__version__, str)

def test_with_newline(tr):
    exp = 'foo\n'
    assert with_newline('foo') == exp
    assert with_newline(exp) == exp

