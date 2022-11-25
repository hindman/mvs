import pytest

from bmv.plan import RenamingPlan

from bmv.constants import (
    CON,
    FAIL,
    STRUCTURES,
)

from bmv.data_objects import BmvError

def assert_failed_because(plan, msg, starts = False):
    stop = len(msg) if starts else None
    fmsgs = tuple(
        f.msg[0 : stop]
        for f in plan.uncontrolled_failures
    )
    assert msg in fmsgs

def test_structure_none(tr):
    origs = ('a', 'b', 'c')
    news = ('a1', 'b1', 'c1')
    plan = RenamingPlan(
        inputs = origs + news,
        file_sys = origs,
    )
    with pytest.raises(BmvError) as einfo:
        plan.rename_paths()
    assert einfo.value.params['msg'] == FAIL.prepare_failed
    assert_failed_because(plan, FAIL.parsing_no_structures)

def test_structure_flat(tr):
    origs = ('a', 'b', 'c')
    news = ('a1', 'b1', 'c1')
    plan = RenamingPlan(
        inputs = origs + news,
        structure = STRUCTURES.flat,
        file_sys = origs,
    )
    plan.rename_paths()
    assert tuple(plan.file_sys) == news

def test_renaming_code(tr):
    origs = ('a', 'b', 'c')
    news = ('aa', 'bb', 'cc')
    plan = RenamingPlan(
        inputs = origs,
        rename_code = 'return o + o',
        file_sys = origs,
    )
    plan.rename_paths()
    assert tuple(plan.file_sys) == news

def test_filtering_code(tr):
    origs = ('a', 'b', 'c', 'd', 'dd')
    news = ('aa', 'bb', 'cc')
    plan = RenamingPlan(
        inputs = origs,
        rename_code = 'return o + o',
        filter_code = 'return "d" not in o',
        file_sys = origs,
    )
    plan.rename_paths()
    assert tuple(plan.file_sys) == ('d', 'dd') + news

def test_seq(tr):
    origs = ('a', 'b', 'c')
    news = ('a.20', 'b.30', 'c.40')
    plan = RenamingPlan(
        inputs = origs,
        rename_code = 'return f"{o}.{seq * 2}"',
        file_sys = origs,
        seq_start = 10,
        seq_step = 5,
    )
    plan.rename_paths()
    assert tuple(plan.file_sys) == news

def test_plan_as_dict(tr):
    # Expected keys in plan.as_dict.
    exp_keys = sorted((
        'inputs',
        'structure',
        'rename_code',
        'filter_code',
        'indent',
        'seq_start',
        'seq_step',
        'file_sys',
        'skip_failed_filter',
        'skip_failed_rename',
        'skip_equal',
        'skip_missing',
        'skip_missing_parent',
        'skip_existing_new',
        'skip_colliding_new',
        'clobber_existing_new',
        'clobber_colliding_new',
        'keep_failed_filter',
        'create_missing_parent',
        'failures',
        'prefix_len',
        'rename_pairs',
    ))

    # Set up plan.
    origs = ('a', 'b', 'c')
    news = ('a.10', 'b.15', 'c.20')
    plan = RenamingPlan(
        inputs = origs,
        structure = None,
        rename_code = 'return f"{o}.{seq}"',
        filter_code = 'return "d" not in o',
        seq_start = 10,
        seq_step = 5,
        file_sys = origs,
    )

    # Check before and after renaming.
    assert sorted(plan.as_dict) == exp_keys
    plan.rename_paths()
    assert tuple(plan.file_sys) == news
    assert sorted(plan.as_dict) == exp_keys

def test_rename_twice(tr):
    # Create a valid plan.
    origs = ('a', 'b', 'c')
    news = ('aa', 'bb', 'cc')
    plan = RenamingPlan(
        inputs = origs,
        rename_code = 'return o + o',
        file_sys = origs,
    )

    # Rename succeeds.
    plan.rename_paths()
    assert tuple(plan.file_sys) == news

    # Second attempt raises and
    with pytest.raises(BmvError) as einfo:
        plan.rename_paths()
    assert einfo.value.params['msg'] == FAIL.rename_done_already
    assert tuple(plan.file_sys) == news

def test_invalid_controls(tr):
    # Paths.
    origs = ('a', 'b', 'c')
    news = ('a1', 'b1', 'c1')

    # Common keyword args.
    common = dict(
        inputs = origs + news,
        structure = STRUCTURES.flat,
        file_sys = origs,
    )

    # Failure control args all set to false.
    all_controls = dict(
        skip_equal = False,
        skip_missing = False,
        skip_missing_parent = False,
        create_missing_parent = False,
        skip_existing_new = False,
        clobber_existing_new = False,
        skip_colliding_new = False,
        clobber_colliding_new = False,
        skip_failed_rename = False,
        skip_failed_filter = False,
        keep_failed_filter = False,
    )

    # The pairs of control flags that can conflict.
    conflicting_pairs = (
        ('skip_missing_parent', 'create_missing_parent'),
        ('skip_existing_new', 'clobber_existing_new'),
        ('skip_colliding_new', 'clobber_colliding_new'),
        ('skip_failed_filter', 'keep_failed_filter'),
    )

    # The renaming scenario works fine.
    plan = RenamingPlan(**common, **all_controls)
    plan.rename_paths()
    assert tuple(plan.file_sys) == news

    # If we try to create a RenamingPlan using any of those
    # pairs both set to true, we get a ValueError.
    for pair in conflicting_pairs:
        conflicting = {k : True for k in pair}
        controls = {**all_controls, **conflicting}
        with pytest.raises(ValueError) as einfo:
            plan = RenamingPlan(**common, **controls)
        msg = str(einfo.value)
        exp = FAIL.conflicting_controls.format(*pair)
        assert msg == exp

def test_missing_orig(tr):
    # Paths.
    origs = ('a', 'b', 'c')
    news = ('a1', 'b1', 'c1')

    # Renaming plan, but file_sy is missing an original path.
    plan = RenamingPlan(
        inputs = origs + news,
        structure = STRUCTURES.flat,
        file_sys = origs[0:-1],
    )

    # Prepare does not raise and it marks the plan as failed.
    # In addition, we can call prepare multiple times.
    plan.prepare()
    plan.prepare()
    assert plan.failed

    # Renaming will raise.
    with pytest.raises(BmvError) as einfo:
        plan.rename_paths()
    assert einfo.value.params['msg'] == FAIL.prepare_failed
    assert_failed_because(plan, FAIL.orig_missing)

