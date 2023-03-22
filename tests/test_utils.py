import pytest

# Import these from the package.
from mvs import RenamingPlan, MvsError, __version__

from mvs.utils import RenamePair

####
# Exercise package's top-level importables.
####

def test_top_level_imports(tr):
    # Exercise the package's top-level importables.
    # Do something simple with each one.
    assert 'a' in RenamingPlan(inputs = ('a', 'b')).inputs
    assert MvsError('foo', x = 1).msg == 'foo'
    assert isinstance(__version__, str)

def test_rename_pair(tr):
    rp = RenamePair('a', 'b')
    assert rp.orig == 'a'
    assert rp.new == 'b'

