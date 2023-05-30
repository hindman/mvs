import pytest

from textwrap import dedent

from mvs.utils import MvsError
from mvs.messages import MSG_FORMATS as MF

from mvs.problems import (
    PROBLEM_NAMES as PN,
    Problem,
    SUMMARY_TABLE,
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

def test_build_summary_table(tr):
    # This function is tested is isolation because the cli.py tests rely on
    # build_summary_table() to assemble expected CLI output.

    # Set up some expected outputs.
    HEADING = 'Renaming plan summary:\n'
    E = dict(
        empty = dedent(f'''
            # {HEADING}
              Total: 0
                Filtered: 0
                Excluded: 0
                Skipped: 0
                Active: 0
        '''),
        ex1 = dedent(f'''
            # {HEADING}
              Total: 110
                Filtered: 20
                Excluded: 30
                  noop-equal: 8
                  code-filter: 13
                  exists-other: 9
                Skipped: 10
                  parent: 7
                  collides-diff: 3
                Active: 50
                  exists: 31
                  ok: 19
        '''),
    )

    # Set up some input params.
    P = dict(
        empty = {},
        unknown = dict(
            fubb = 99,
            blort = 88,
        ),
        ex1 = dict(
            total = 110,
            filtered = 20,
            excluded = 30,
            noop_equal = 8,
            code_filter = 13,
            exists_other = 9,
            skipped = 10,
            parent = 7,
            collides_diff = 3,
            active = 50,
            active_exists = 31,
            ok = 19,
        ),
    )
    P['empty_unknown'] = P['unknown']
    P['ex1_unknown'] = {**P['ex1'], **P['unknown']}

    # Setup up some testing scenarios mapping P => E.
    TESTS = dict(
        empty = 'empty',
        unknown = 'empty',
        ex1 = 'ex1',
        empty_unknown = 'empty',
        ex1_unknown = 'ex1',
    )

    # Test.
    for pk, ek in TESTS.items():
        params = P[pk]
        exp = E[ek]
        got = build_summary_table(params)
        assert (pk, ek, got) == (pk, ek, exp)

