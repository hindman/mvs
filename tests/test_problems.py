import pytest

from mvs.utils import MvsError
from mvs.messages import MSG_FORMATS as MF

from mvs.problems import (
    Problem,
    PROBLEM_NAMES as PN,
    StrictMode,
)

def test_from_skip_id(tr):
    # Basic usages.
    p = Problem.from_skip_id('exists')
    assert p.name == 'exists'
    assert p.variety is None
    p = Problem.from_skip_id('exists-diff')
    assert p.name == 'exists'
    assert p.variety == 'diff'

    # Invalid usages.
    invalids = ('exists-diff-blort', 'missing')
    for sid in invalids:
        with pytest.raises(MvsError) as einfo:
            p = Problem.from_skip_id(sid)
        assert einfo.value.msg == MF.invalid_skip.format(sid)

def test_strict_mode(tr):
    # One problem.
    sm = StrictMode.from_user('exists')
    assert sm.excluded is False
    assert sm.probs == ('exists',)

    # Multiple, plus excluded.
    sm = StrictMode.from_user('exists collides excluded')
    assert sm.excluded is True
    assert sm.probs == ('exists', 'collides')

    # All.
    sm = StrictMode.from_user('all')
    assert sm.excluded is True
    assert sm.probs == StrictMode.STRICT_PROBS

    # Invalid.
    invalid = 'exists foo'
    with pytest.raises(MvsError) as einfo:
        sm = StrictMode.from_user(invalid)
    exp = MF.invalid_strict.format(invalid)
    assert einfo.value.msg == exp

