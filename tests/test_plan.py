import pytest
from itertools import chain

from bmv.plan import RenamingPlan

from bmv.constants import (
    CON,
    FAIL,
    STRUCTURES,
)

from bmv.data_objects import BmvError, UserCodeExecFailure

def assert_failed_because(einfo, plan, msg, i = None):
    fmsgs = tuple(
        f.msg[0 : i]
        for f in plan.uncontrolled_failures
    )
    assert einfo.value.params['msg'] == FAIL.prepare_failed
    assert msg[0 : i] in fmsgs

def test_structure_none(tr):
    origs = ('a', 'b', 'c')
    news = ('a1', 'b1', 'c1')
    plan = RenamingPlan(
        inputs = origs + news,
        file_sys = origs,
    )
    assert plan.structure == STRUCTURES.flat
    plan.rename_paths()
    assert tuple(plan.file_sys) == news

def test_no_inputs(tr):
    plan = RenamingPlan(
        inputs = [],
        structure = STRUCTURES.flat,
        file_sys = [],
    )
    with pytest.raises(BmvError) as einfo:
        plan.rename_paths()
    assert_failed_because(einfo, plan, FAIL.no_input_paths)

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

def test_structure_paragraphs(tr):
    # Paths.
    origs = ('a', 'b', 'c')
    empty = ('', '')
    news = ('a1', 'b1', 'c1')

    # Basic.
    plan = RenamingPlan(
        inputs = origs + empty + news,
        structure = STRUCTURES.paragraphs,
        file_sys = origs,
    )
    plan.rename_paths()
    assert tuple(plan.file_sys) == news

    # Additional empty lines.
    plan = RenamingPlan(
        inputs = empty + origs + empty + news + empty,
        structure = STRUCTURES.paragraphs,
        file_sys = origs,
    )
    plan.rename_paths()
    assert tuple(plan.file_sys) == news

    # Odd number of paragraphs.
    plan = RenamingPlan(
        inputs = origs[0:1] + empty + origs[1:] + empty + news,
        structure = STRUCTURES.paragraphs,
        file_sys = origs,
    )
    with pytest.raises(BmvError) as einfo:
        plan.rename_paths()
    assert_failed_because(einfo, plan, FAIL.parsing_paragraphs)

def test_structure_pairs(tr):
    # Paths.
    origs = ('a', 'b', 'c')
    empty = ('', '')
    news = ('a1', 'b1', 'c1')
    inputs = tuple(chain(*zip(origs, news)))

    # Basic.
    plan = RenamingPlan(
        inputs = inputs,
        structure = STRUCTURES.pairs,
        file_sys = origs,
    )
    plan.rename_paths()
    assert tuple(plan.file_sys) == news

    # Additional empty lines.
    plan = RenamingPlan(
        inputs = empty + inputs[:4] + empty + inputs[4:] + empty,
        structure = STRUCTURES.pairs,
        file_sys = origs,
    )
    plan.rename_paths()
    assert tuple(plan.file_sys) == news

    # Odd number of paths.
    plan = RenamingPlan(
        inputs = inputs[:-1],
        structure = STRUCTURES.pairs,
        file_sys = origs,
    )
    with pytest.raises(BmvError) as einfo:
        plan.rename_paths()
    assert_failed_because(einfo, plan, FAIL.parsing_inequality)

def test_structure_rows(tr):
    # Paths.
    origs = ('a', 'b', 'c')
    empty = ('', '')
    news = ('a1', 'b1', 'c1')
    inputs = tuple(f'{o}\t{n}' for o, n in zip(origs, news))

    # Basic.
    plan = RenamingPlan(
        inputs = empty + inputs + empty,
        structure = STRUCTURES.rows,
        file_sys = origs,
    )
    plan.rename_paths()
    assert tuple(plan.file_sys) == news

    # Odd number of cells in a row.
    plan = RenamingPlan(
        inputs = inputs[:-1] + ('c\t',),
        structure = STRUCTURES.rows,
        file_sys = origs,
    )
    with pytest.raises(BmvError) as einfo:
        plan.rename_paths()
    assert_failed_because(einfo, plan, FAIL.parsing_row, i = 55)

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

def test_code_compilation_fails(tr):
    # Paths and a snippet of invalid code.
    origs = ('a', 'b', 'c')
    news = ('aa', 'bb', 'cc')
    bad_code = 'FUBB BLORT'

    # Helper to check the plan's failures.
    def do_checks(p):
        with pytest.raises(BmvError) as einfo:
            p.rename_paths()
        assert einfo.value.params['msg'] == FAIL.prepare_failed
        f = p.uncontrolled_failures[0]
        assert isinstance(f, UserCodeExecFailure)
        assert bad_code in f.msg
        assert 'invalid syntax' in f.msg

    # Scenario: invalid renaming code.
    plan = RenamingPlan(
        inputs = origs,
        structure = STRUCTURES.flat,
        rename_code = bad_code,
        file_sys = origs,
    )
    do_checks(plan)

    # Scenario: invalid filtering code.
    plan = RenamingPlan(
        inputs = origs + news,
        structure = STRUCTURES.flat,
        filter_code = bad_code,
        file_sys = origs,
    )
    do_checks(plan)

def test_code_execution_fails(tr):
    # Paths and code that will cause the second RenamePair to fail
    # during execution of user code.
    origs = ('a', 'b', 'c')
    news = ('aa', 'bb', 'cc')
    rename_code1 = 'return FUBB if seq == 2 else o + o'
    rename_code2 = 'return 9999 if seq == 2 else o + o'
    filter_code = 'return FUBB if seq == 2 else True'
    exp_rp_fails = [False, True, False]

    # Run the scenario for renaming.
    plan = RenamingPlan(
        inputs = origs,
        rename_code = rename_code1,
        file_sys = origs,
    )
    plan.prepare()
    with pytest.raises(BmvError) as einfo:
        plan.rename_paths()
    assert_failed_because(einfo, plan, FAIL.rename_code_invalid, i = 36)
    rp_fails = [rp.failed for rp in plan.rps]
    assert rp_fails == exp_rp_fails

    # Run the other scenario for renaming: return bad data type.
    plan = RenamingPlan(
        inputs = origs,
        rename_code = rename_code2,
        file_sys = origs,
    )
    plan.prepare()
    with pytest.raises(BmvError) as einfo:
        plan.rename_paths()
    assert_failed_because(einfo, plan, FAIL.rename_code_bad_return, i = 45)
    rp_fails = [rp.failed for rp in plan.rps]
    assert rp_fails == exp_rp_fails

    # Run the scenario for filtering.
    plan = RenamingPlan(
        inputs = origs + news,
        structure = STRUCTURES.flat,
        filter_code = filter_code,
        file_sys = origs,
    )
    plan.prepare()
    with pytest.raises(BmvError) as einfo:
        plan.rename_paths()
    assert_failed_because(einfo, plan, FAIL.filter_code_invalid, i = 37)
    rp_fails = [rp.failed for rp in plan.rps]
    assert rp_fails == exp_rp_fails

    # Run the scenario for filtering, keeping those that fail during filtering.
    plan = RenamingPlan(
        inputs = origs + news,
        structure = STRUCTURES.flat,
        filter_code = filter_code,
        file_sys = origs,
        keep_failed_filter = True,
    )
    plan.prepare()
    plan.rename_paths()
    assert tuple(plan.file_sys) == news

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
        'skip_equal',
        'skip_missing',
        'skip_missing_parent',
        'create_missing_parent',
        'skip_existing_new',
        'clobber_existing_new',
        'skip_colliding_new',
        'clobber_colliding_new',
        'skip_failed_rename',
        'skip_failed_filter',
        'keep_failed_filter',
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

def test_prepare_rename_multiple_times(tr):
    # Setup.
    origs = ('a', 'b', 'c')
    news = ('a1', 'b1', 'c1')
    plan = RenamingPlan(
        inputs = origs + news,
        structure = STRUCTURES.flat,
        file_sys = origs,
    )

    # Can call prepare multiple times.
    plan.prepare()
    plan.prepare()

    # Renaming plan works.
    plan.rename_paths()
    assert tuple(plan.file_sys) == news

    # Cannot call rename_paths multiple times.
    with pytest.raises(BmvError) as einfo:
        plan.rename_paths()
    assert einfo.value.params['msg'] == FAIL.rename_done_already

def test_equal(tr):
    # Paths.
    d = ('d',)
    origs = ('a', 'b', 'c') + d
    news = ('a1', 'b1', 'c1') + d
    inputs = origs + news
    file_sys = origs
    exp_file_sys = d + news[:-1]

    # Renaming plan, but with one pair where orig equals new.
    plan = RenamingPlan(
        inputs = inputs,
        structure = STRUCTURES.flat,
        file_sys = origs,
    )

    # Renaming will raise.
    plan.prepare()
    with pytest.raises(BmvError) as einfo:
        plan.rename_paths()
    assert_failed_because(einfo, plan, FAIL.orig_new_same)

    # Renaming will succeed if we skip the offending paths.
    plan = RenamingPlan(
        inputs = inputs,
        structure = STRUCTURES.flat,
        file_sys = file_sys,
        skip_equal = True,
    )
    plan.rename_paths()
    assert tuple(plan.file_sys) == exp_file_sys

def test_missing_orig(tr):
    # Paths.
    origs = ('a', 'b', 'c')
    news = ('a1', 'b1', 'c1')
    file_sys = origs[0:-1]
    exp_file_sys = news[0:-1]

    # Renaming plan, but file_sy is missing an original path.
    plan = RenamingPlan(
        inputs = origs + news,
        structure = STRUCTURES.flat,
        file_sys = file_sys,
    )

    # Prepare does not raise and it marks the plan as failed.
    plan.prepare()
    assert plan.failed

    # Renaming will raise.
    with pytest.raises(BmvError) as einfo:
        plan.rename_paths()
    assert_failed_because(einfo, plan, FAIL.orig_missing)

    # Renaming will succeed if we skip the offending paths.
    plan = RenamingPlan(
        inputs = origs + news,
        structure = STRUCTURES.flat,
        file_sys = file_sys,
        skip_missing = True,
    )
    plan.rename_paths()
    assert tuple(plan.file_sys) == exp_file_sys

def test_new_exists(tr):
    # Paths.
    origs = ('a', 'b', 'c')
    news = ('a1', 'b1', 'c1')
    file_sys = origs + news[1:2]
    exp_file_sys = ('b', 'b1', 'a1', 'c1')

    # Renaming plan, but file_sy is missing an original path.
    plan = RenamingPlan(
        inputs = origs + news,
        structure = STRUCTURES.flat,
        file_sys = file_sys,
    )

    # Prepare does not raise and it marks the plan as failed.
    plan.prepare()
    assert plan.failed

    # Renaming will raise.
    with pytest.raises(BmvError) as einfo:
        plan.rename_paths()
    assert_failed_because(einfo, plan, FAIL.new_exists)

    # Renaming will succeed if we skip the offending paths.
    plan = RenamingPlan(
        inputs = origs + news,
        structure = STRUCTURES.flat,
        file_sys = file_sys,
        skip_existing_new = True,
    )
    plan.rename_paths()
    assert tuple(plan.file_sys) == exp_file_sys

    # Renaming will succeed if we clobber the offending paths.
    plan = RenamingPlan(
        inputs = origs + news,
        structure = STRUCTURES.flat,
        file_sys = file_sys,
        clobber_existing_new = True,
    )
    plan.rename_paths()
    assert tuple(plan.file_sys) == exp_file_sys[1:]

def test_new_parent_missing(tr):
    # Paths.
    origs = ('a', 'b', 'c')
    news = ('xy/tmp/a1', 'b1', 'c1')
    parents = ('xy/tmp', 'xy', '.')
    file_sys = origs
    exp_file_sys1 = ('a', 'b1', 'c1')
    exp_file_sys2 = parents + news

    # Renaming plan, but file_sy is missing an original path.
    plan = RenamingPlan(
        inputs = origs + news,
        structure = STRUCTURES.flat,
        file_sys = file_sys,
    )

    # Prepare does not raise and it marks the plan as failed.
    plan.prepare()
    assert plan.failed

    # Renaming will raise.
    with pytest.raises(BmvError) as einfo:
        plan.rename_paths()
    assert_failed_because(einfo, plan, FAIL.new_parent_missing)

    # Renaming will succeed if we skip the offending paths.
    plan = RenamingPlan(
        inputs = origs + news,
        structure = STRUCTURES.flat,
        file_sys = file_sys,
        skip_missing_parent = True,
    )
    plan.rename_paths()
    assert tuple(plan.file_sys) == exp_file_sys1

    # Renaming will succeed if we skip the offending paths.
    plan = RenamingPlan(
        inputs = origs + news,
        structure = STRUCTURES.flat,
        file_sys = file_sys,
        create_missing_parent = True,
    )
    plan.rename_paths()
    assert tuple(plan.file_sys) == exp_file_sys2

def test_news_collide(tr):
    # Paths.
    origs = ('a', 'b', 'c')
    news = ('a1', 'b1', 'a1')
    file_sys = origs
    exp_file_sys1 = ('a', 'c', 'b1')
    exp_file_sys2 = ('a1', 'b1')

    # Renaming plan with collision among the new paths.
    plan = RenamingPlan(
        inputs = origs + news,
        structure = STRUCTURES.flat,
        file_sys = file_sys,
    )

    # Prepare does not raise and it marks the plan as failed.
    plan.prepare()
    assert plan.failed

    # Renaming will raise.
    with pytest.raises(BmvError) as einfo:
        plan.rename_paths()
    assert_failed_because(einfo, plan, FAIL.new_collision)

    # Renaming will succeed if we skip the offending paths.
    plan = RenamingPlan(
        inputs = origs + news,
        structure = STRUCTURES.flat,
        file_sys = file_sys,
        skip_colliding_new = True,
    )
    plan.rename_paths()
    assert tuple(plan.file_sys) == exp_file_sys1

    # Renaming will succeed if we skip the offending paths.
    plan = RenamingPlan(
        inputs = origs + news,
        structure = STRUCTURES.flat,
        file_sys = file_sys,
        clobber_colliding_new = True,
    )
    plan.rename_paths()
    assert tuple(plan.file_sys) == exp_file_sys2

def test_failures_skip_all(tr):
    # Paths.
    origs = ('a', 'b', 'c')
    news = ('Z', 'Z', 'Z')

    # Renaming plan, but where all news collide.
    plan = RenamingPlan(
        inputs = origs + news,
        structure = STRUCTURES.flat,
        file_sys = origs,
        skip_colliding_new = True,
    )

    # Renaming will raise.
    plan.prepare()
    with pytest.raises(BmvError) as einfo:
        plan.rename_paths()
    assert_failed_because(einfo, plan, FAIL.no_paths_after_processing)

def test_file_sys_arg(tr):
    # Paths.
    origs = ('a', 'b', 'c')
    news = ('a1', 'b1', 'a1')

    # Pass file_sys as a sequence. We do this to generate the
    # expected file_sys for an ensuing test.
    plan = RenamingPlan(
        inputs = origs + news,
        structure = STRUCTURES.flat,
        file_sys = origs,
    )
    file_sys = plan.file_sys

    # Pass file_sys as None: works fine.
    plan = RenamingPlan(
        inputs = origs + news,
        structure = STRUCTURES.flat,
        file_sys = None,
    )
    assert plan.file_sys is None

    # Pass file_sys as a dict: we expect an
    # indepentent dict equal to the original.
    plan = RenamingPlan(
        inputs = origs + news,
        structure = STRUCTURES.flat,
        file_sys = file_sys,
    )
    assert plan.file_sys == file_sys
    assert plan.file_sys is not file_sys

def test_common_prefix(tr):
    # Paths.
    origs = ('blah-a', 'blah-b', 'blah-c')
    exp_file_sys = ('a', 'b', 'c')

    # Basic.
    plan = RenamingPlan(
        inputs = origs,
        rename_code = 'return plan.strip_prefix(o)',
        file_sys = origs,
    )
    plan.rename_paths()
    assert tuple(plan.file_sys) == exp_file_sys

