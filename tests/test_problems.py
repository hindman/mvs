import pytest

from mvs.utils import MvsError
from mvs.messages import MSG_FORMATS as MF

from mvs.problems import (
    PROBLEM_NAMES as PN,
    Problem,
    StrictMode,
    build_summary_table,
)

def test_from_str_id(tr):
    # Basic usages.
    p = Problem.from_sid('exists')
    assert p.name == 'exists'
    assert p.variety is None
    p = Problem.from_sid('exists-diff')
    assert p.name == 'exists'
    assert p.variety == 'diff'

    # Invalid usages.
    invalids = ('exists-fubb', 'blort-foo')
    for sid in invalids:
        with pytest.raises(MvsError) as einfo:
            p = Problem.from_sid(sid)
        assert einfo.value.msg == MF.invalid_problem.format(*sid.split('-'))

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

def test_summary_table(tr):
    # TODO.
    return
    params = dict(ok = 10, filtered = 32, code_filter = 3, exists_other = 3, collides_diff = 4)
    xs = build_summary_table(params)
    tr.dump(xs)

