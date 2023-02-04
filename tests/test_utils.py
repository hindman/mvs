import pytest

from mvs.utils import RenamePair

def test_rename_pair(tr):
    rp = RenamePair('a', 'b')
    assert rp.orig == 'a'
    assert rp.new == 'b'

