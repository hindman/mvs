import pytest

from bmv import (
    __version__,
)

from bmv.cli import (
    RenamePair,
    ValidationFailure,
    validate_rename_pairs,
    CON,
)

def test_version(tr):
    # Most just a test that we can import __version__ from bmv package.
    assert isinstance(__version__, str)

def tuples_to_rename_pairs(tups, root = ''):
    # Helper used when checking validation code.
    return tuple(
        RenamePair(root + orig, root + new)
        for orig, new in tups
    )

def test_validation_orig_existence(tr):
    # Original path should exist.
    tups = (
        ('d1', 'dA'),
        ('d2', 'dB'),
        ('d88', 'dYY'),  # Orig does not exist.
        ('d99', 'dZZ'),  # Ditto.
    )
    rps = tuples_to_rename_pairs(tups, root = tr.WORK_AREA_ROOT)
    fails = validate_rename_pairs(rps)
    assert len(fails) == 2
    assert fails[-2].rp is rps[-2]
    assert fails[-1].rp is rps[-1]
    assert fails[-2].msg == CON.fail_orig_missing
    assert fails[-1].msg == CON.fail_orig_missing

def test_validation_new_nonexistence(tr):
    # New should not exist.
    tups = (
        ('d1', 'dA'),
        ('d2', 'd1'),   # New already exists.
    )
    rps = tuples_to_rename_pairs(tups, root = tr.WORK_AREA_ROOT)
    fails = validate_rename_pairs(rps)
    assert len(fails) == 1
    assert fails[0].rp is rps[1]
    assert fails[0].msg == CON.fail_new_exists

def test_validation_new_parent_existence(tr):
    # Parent of new should exist.
    tups = (
        ('d1', 'fubb/dA'),  # Parent of new does not exist.
        ('d2', 'dB'),
    )
    rps = tuples_to_rename_pairs(tups, root = tr.WORK_AREA_ROOT)
    fails = validate_rename_pairs(rps)
    assert len(fails) == 1
    assert fails[0].rp is rps[0]
    assert fails[0].msg == CON.fail_new_parent_missing

def test_validation_orig_and_new_difference(tr):
    # Original and new should differ.
    tups = (
        ('d1', 'dA'),
        ('d1/aa.txt', 'd1/aa.txt'),  # Orig and new are the same (and new exists).
        ('d2', 'dB'),
    )
    rps = tuples_to_rename_pairs(tups, root = tr.WORK_AREA_ROOT)
    fails = validate_rename_pairs(rps)
    assert len(fails) == 2
    assert fails[0].rp is rps[1]
    assert fails[1].rp is rps[1]
    assert fails[0].msg == CON.fail_new_exists
    assert fails[1].msg == CON.fail_orig_new_same

def test_validation_new_uniqueness(tr):
    # News should not collide among themselves.
    tups = (
        ('d1', 'dA'),
        ('d2/aa.txt', 'd2/foo_txt'),  # New paths collide with each other.
        ('d2/dd.txt', 'd2/foo_txt'),  # Ditto.
    )
    rps = tuples_to_rename_pairs(tups, root = tr.WORK_AREA_ROOT)
    fails = validate_rename_pairs(rps)
    assert len(fails) == 2
    assert fails[0].rp is rps[1]
    assert fails[1].rp is rps[2]
    assert fails[0].msg == CON.fail_new_collision
    assert fails[1].msg == CON.fail_new_collision

