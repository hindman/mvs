import pytest
from itertools import chain

# Top-level package imports.
from mvs import RenamingPlan, MvsError, __version__

# Imports for testing.
from mvs.utils import CON, STRUCTURES, MSG_FORMATS as MF
from mvs.problems import (
    CONTROLLABLES,
    CONTROLS,
    PROBLEM_NAMES as PN,
    Problem,
)

####
# Exercise package's top-level importables.
####

def test_top_level_imports(tr):
    # Do something simple with each top-level import.
    assert 'a' in RenamingPlan(inputs = ('a', 'b')).inputs
    assert MvsError('foo', x = 1).msg == 'foo'
    assert isinstance(__version__, str)

####
# Helper to confirm that a RenamingPlan raised for the expected reason.
####

def assert_raised_because(einfo, plan, pname):
    # Takes (1) an einfo for an exception that was raised by,
    # (2) the given RenamingPlan, and (3) an expected Problem name.

    # Get the part of the Problem message format before any string formatting.
    exp_msg = Problem.format_for(pname).split('{')[0]
    size = len(exp_msg)

    # Grab the plan's uncontrolled failure messages, trimmed to the same size.
    fmsgs = tuple(
        f.msg[0 : size]
        for f in plan.uncontrolled_problems
    )

    # Check for the expected (a) general failure message
    # and (b) specific Problem message.
    assert einfo.value.params['msg'] == MF.prepare_failed
    assert exp_msg in fmsgs

####
# Inputs and their structures.
####

def test_no_inputs(tr):
    # If given no inputs, prepare() will fail
    # and rename_paths() will raise.
    plan = RenamingPlan(inputs = ())
    plan.prepare()
    assert plan.failed
    with pytest.raises(MvsError) as einfo:
        plan.rename_paths()
    assert_raised_because(einfo, plan, PN.parsing_no_paths)

def test_structure_default(tr, create_wa):
    # A RenamingPlan defaults to flat input structure,
    # or the user can request flat explicitly.
    origs = ('a', 'b', 'c')
    news = ('a1', 'b1', 'c1')
    structs = (None, STRUCTURES.flat)
    for s in structs:
        wa = create_wa(origs, news)
        plan = RenamingPlan(
            inputs = wa.origs + wa.news,
            structure = s,
        )
        assert plan.structure == STRUCTURES.flat
        plan.rename_paths()
        wa.check()

def test_structure_paragraphs(tr, create_wa):
    # Paths, etc.
    origs = ('a', 'b', 'c')
    news = ('a1', 'b1', 'c1')
    empty = ('', '')
    struct = STRUCTURES.paragraphs

    # Helper.
    def do_check(n, before = False, after = False):
        include_empties = {
            False: (),
            True: empty,
        }
        wa = create_wa(origs, news)
        inputs = (
            include_empties[before] +
            wa.origs +
            empty[0:n] +
            wa.news +
            include_empties[after]
        )
        plan = RenamingPlan(
            inputs = inputs,
            structure = struct,
        )
        plan.rename_paths()
        wa.check()

    # Basic use cases: varying N of empty lines between origs and news,
    # optionally with empty lines before and after.
    do_check(1)
    do_check(2)
    do_check(1, before = True)
    do_check(2, after = True)
    do_check(1, before = True, after = True)

    # Helper.
    def do_check_raise(n_para):
        wa = create_wa(origs, news)
        if n_para == 3:
            inputs = wa.origs + empty + wa.news[0:1] + empty + wa.news[1:]
        else:
            inputs = wa.origs + wa.news
        plan = RenamingPlan(
            inputs = inputs,
            structure = struct,
        )
        with pytest.raises(MvsError) as einfo:
            plan.rename_paths()
        assert_raised_because(einfo, plan, PN.parsing_paragraphs)
        wa.check(no_change = True)

    # Cases that will raise due to an odd N of paragraphs (1 then 3).
    # In both cases, there are equal numbers of origs vs news.
    do_check_raise(1)
    do_check_raise(3)

def test_structure_pairs(tr, create_wa):
    # Paths, etc.
    origs = ('a', 'b', 'c')
    news = ('a1', 'b1', 'c1')
    empty = ('', '')
    struct = STRUCTURES.pairs

    # Helper to organize WorkArea paths as orig-new pairs.
    def as_pairs(wa):
        pairs = zip(wa.origs, wa.news)
        return tuple(chain(*pairs))

    # Basic use case: inputs as orig-new pairs.
    wa = create_wa(origs, news)
    inputs = as_pairs(wa)
    plan = RenamingPlan(
        inputs = inputs,
        structure = struct,
    )
    plan.rename_paths()
    wa.check()

    # Same, but empty lines in various spots.
    wa = create_wa(origs, news)
    inputs = as_pairs(wa)
    inputs = empty + inputs[:2] + empty + inputs[2:] + empty
    plan = RenamingPlan(
        inputs = inputs,
        structure = struct,
    )
    plan.rename_paths()
    wa.check()

    # Odd number of paths: should raise.
    wa = create_wa(origs, news)
    inputs = as_pairs(wa)[:-1]
    plan = RenamingPlan(
        inputs = inputs,
        structure = struct,
    )
    with pytest.raises(MvsError) as einfo:
        plan.rename_paths()
    assert_raised_because(einfo, plan, PN.parsing_imbalance)
    wa.check(no_change = True)

def test_structure_rows(tr, create_wa):
    # Paths.
    origs = ('a', 'b', 'c')
    empty = ('', '')
    news = ('a1', 'b1', 'c1')
    struct = STRUCTURES.rows

    # Helper to organize WorkArea paths as rows.
    def as_rows(wa, fmt = '{}\t{}'):
        inputs = tuple(
            fmt.format(o, n)
            for o, n in  zip(wa.origs, wa.news)
        )
        return empty + inputs + empty

    # Basic use case with row inputs.
    wa = create_wa(origs, news)
    plan = RenamingPlan(
        inputs = as_rows(wa),
        structure = struct,
    )
    plan.rename_paths()
    wa.check()

    # Cases that should raise du to invalid row formats:
    # empty cells, odd number of cells, or both.
    bad_formats = (
        '{}\t',
        '{}\t\t{}',
        '{}\t{}\t',
        '\t{}\t{}',
    )
    for fmt in bad_formats:
        wa = create_wa(origs, news)
        plan = RenamingPlan(
            inputs = as_rows(wa, fmt),
            structure = struct,
        )
        with pytest.raises(MvsError) as einfo:
            plan.rename_paths()
        assert_raised_because(einfo, plan, PN.parsing_row)
        wa.check(no_change = True)

####
# User-supplied code.
####

def test_renaming_code(tr, create_wa):
    # Paths and three variants of renaming code.
    origs = ('a', 'b', 'c')
    news = ('aa', 'bb', 'cc')
    code_str = 'return o + o'
    code_lambda = lambda o, p, seq, plan: o + o
    def code_func(o, p, seq, plan): return o + o

    # Basic use case: generate new-paths via user-supplied code.
    for code in (code_str, code_lambda, code_func):
        wa = create_wa(origs, news, rootless = True)
        plan = RenamingPlan(
            inputs = wa.origs,
            rename_code = code,
        )
        with wa.cd():
            plan.rename_paths()
        wa.check()

def test_filtering_code(tr, create_wa):
    # Filter orig paths with user-supplied code.
    origs = ('a', 'b', 'c')
    news = ('aa', 'bb', 'cc')
    extras = ('d', 'dd', 'xyz/')
    wa = create_wa(origs, news, extras, rootless = True)
    plan = RenamingPlan(
        inputs = wa.origs + wa.extras,
        rename_code = 'return o + o',
        filter_code = 'return not ("d" in o or p.is_dir())',
    )
    with wa.cd():
        plan.rename_paths()
    wa.check()

def test_code_compilation_fails(tr, create_wa):
    # Paths and a snippet of invalid code.
    origs = ('a', 'b', 'c')
    news = ('aa', 'bb', 'cc')
    bad_code = 'FUBB BLORT'

    # Helper to check the plan's failures.
    def do_checks(wa, plan):
        with pytest.raises(MvsError) as einfo:
            plan.rename_paths()
        assert einfo.value.params['msg'] == MF.prepare_failed
        f = plan.uncontrolled_problems[0]
        assert f.name == PN.user_code_exec
        assert bad_code in f.msg
        assert 'invalid syntax' in f.msg
        wa.check(no_change = True)

    # Scenario: invalid renaming code.
    wa = create_wa(origs, news)
    plan = RenamingPlan(
        inputs = wa.origs,
        rename_code = bad_code,
    )
    do_checks(wa, plan)

    # Scenario: invalid filtering code.
    wa = create_wa(origs, news)
    plan = RenamingPlan(
        inputs = wa.origs + wa.news,
        filter_code = bad_code,
    )
    do_checks(wa, plan)

def test_code_execution_fails(tr, create_wa):
    # Paths and code that will cause the second RenamePair
    # to fail during execution of user code.
    origs = ('a', 'b', 'c')
    news = ('aa', 'bb', 'cc')
    rename_code1 = 'return FUBB if seq == 2 else o + o'
    rename_code2 = 'return 9999 if seq == 2 else o + o'
    filter_code = 'return FUBB if seq == 2 else True'
    exp_rp_fails = [False, True, False]

    # Helper try to rename paths and then check the plan's failures.
    def do_checks(wa, plan, pname):
        with pytest.raises(MvsError) as einfo:
            with wa.cd():
                plan.rename_paths()
        assert_raised_because(einfo, plan, pname)
        fails = plan.uncontrolled_problems
        assert len(fails) == 1
        f = fails[0]
        assert f.name == pname
        assert f.rp.orig == 'b'
        wa.check(no_change = True)

    # Scenario: renaming code raises an exception.
    wa = create_wa(origs, news, rootless = True)
    plan = RenamingPlan(
        inputs = wa.origs,
        rename_code = rename_code1,
    )
    do_checks(wa, plan, PN.rename_code_invalid)

    # Scenario: renaming code returns bad data type.
    wa = create_wa(origs, news, rootless = True)
    plan = RenamingPlan(
        inputs = wa.origs,
        rename_code = rename_code2,
    )
    do_checks(wa, plan, PN.rename_code_bad_return)

    # Scenario: filtering code raises an exception.
    wa = create_wa(origs, news, rootless = True)
    plan = RenamingPlan(
        inputs = wa.origs + wa.news,
        filter_code = filter_code,
    )
    do_checks(wa, plan, PN.filter_code_invalid)

def test_seq(tr, create_wa):
    # User defines a sequence and uses its values in user-supplied code.
    origs = ('a', 'b', 'c')
    news = ('a.20', 'b.30', 'c.40')
    wa = create_wa(origs, news, rootless = True)
    plan = RenamingPlan(
        inputs = wa.origs,
        rename_code = 'return f"{o}.{seq * 2}"',
        seq_start = 10,
        seq_step = 5,
    )
    with wa.cd():
        plan.rename_paths()
    wa.check()

def test_common_prefix(tr, create_wa):
    # User-supplied code exercises strip_prefix() helper.
    origs = ('blah-a', 'blah-b', 'blah-c')
    news = ('a', 'b', 'c')
    wa = create_wa(origs, news, rootless = True)
    plan = RenamingPlan(
        inputs = wa.origs,
        rename_code = 'return plan.strip_prefix(o)',
    )
    with wa.cd():
        plan.rename_paths()
    wa.check()

####
# RenamingPlan data.
####

def test_plan_as_dict(tr, create_wa):
    # Expected keys in plan.as_dict.
    exp_keys = sorted((
        'inputs',
        'structure',
        'rename_code',
        'filter_code',
        'indent',
        'seq_start',
        'seq_step',
        'controls',
        # 'skip',
        # 'clobber',
        # 'create',
        'problems',
        'prefix_len',
        'rename_pairs',
        'tracking_index',
    ))

    # Set up plan.
    origs = ('a', 'b', 'c')
    news = ('a.10', 'b.15', 'c.20')
    wa = create_wa(origs, news, rootless = True)
    plan = RenamingPlan(
        inputs = wa.origs,
        rename_code = 'return f"{o}.{seq}"',
        filter_code = 'return "d" not in o',
        seq_start = 10,
        seq_step = 5,
    )

    # Check before and after renaming.
    assert sorted(plan.as_dict) == exp_keys
    with wa.cd():
        plan.rename_paths()
    wa.check()
    assert sorted(plan.as_dict) == exp_keys

####
# Check unexpected usage scenarios.
####

def test_prepare_rename_multiple_times(tr, create_wa):
    # Setup.
    origs = ('a', 'b', 'c')
    news = ('a1', 'b1', 'c1')
    wa = create_wa(origs, news)
    plan = RenamingPlan(
        inputs = wa.origs + wa.news,
    )

    # Can call prepare multiple times.
    plan.prepare()
    plan.prepare()

    # Renaming plan works.
    plan.rename_paths()
    wa.check()

    # Cannot call rename_paths multiple times.
    with pytest.raises(MvsError) as einfo:
        plan.rename_paths()
    assert einfo.value.params['msg'] == MF.rename_done_already
    wa.check()

####
# Problems and problem-control.
####

def test_invalid_controls(tr, create_wa):
    # Paths.
    origs = ('a', 'b', 'c')
    news = ('a1', 'b1', 'c1')

    # Base scenario: it works fine.
    # In addition, we will re-use the inputs defined here
    # in subsequent tests, which don't need a WorkArea
    # because the RenamingPlan will raise during initialization.
    wa = create_wa(origs, news)
    inputs = wa.origs + wa.news
    plan = RenamingPlan(inputs)
    plan.rename_paths()
    wa.check()

    # Scenarios: can configure problem-control in various ways.
    all_controls = CONTROLLABLES[CONTROLS.skip]
    checks = (
        ('all', all_controls),
        ('first2', all_controls[0:2]),
    )
    for label, controls in checks:
        tup = tuple(f'skip-{c}' for c in controls)
        plan1 = RenamingPlan(inputs, controls = tup)
        plan2 = RenamingPlan(inputs, controls = ' '.join(tup))
        assert (label, plan1.controls) == (label, tup)
        assert (label, plan2.controls) == (label, tup)

    # But we cannot control the same problem in two different ways.
    checks = (
        (PN.parent, CONTROLS.skip, CONTROLS.create),
        (PN.existing, CONTROLS.skip, CONTROLS.clobber),
        (PN.colliding, CONTROLS.skip, CONTROLS.clobber),
    )
    for pname, *controls in checks:
        tup = tuple(f'{c}-{pname}' for c in controls)
        with pytest.raises(MvsError) as einfo:
            plan = RenamingPlan(inputs, controls = tup)
        msg = einfo.value.params['msg']
        exp = MF.conflicting_controls.format(pname, *controls)
        assert msg == exp

    # And we cannot control a problem in an inappropriate way.
    checks = (
        (PN.equal, CONTROLS.clobber),
        (PN.missing, CONTROLS.create),
        (PN.parent, CONTROLS.clobber),
    )
    for pname, control in checks:
        pc_name = f'{control}-{pname}'
        with pytest.raises(MvsError) as einfo:
            plan = RenamingPlan(inputs, controls = pc_name)
        msg = einfo.value.params['msg']
        exp = MF.invalid_control.format(pc_name)
        assert msg == exp

def test_equal(tr, create_wa):
    # Paths where an orig path equals its new counterpart.
    d = ('d',)
    origs = ('a', 'b', 'c') + d
    news = ('a1', 'b1', 'c1') + d

    # Renaming attempt will raise.
    wa = create_wa(origs, news)
    plan = RenamingPlan(
        inputs = wa.origs + wa.news,
    )
    with pytest.raises(MvsError) as einfo:
        plan.rename_paths()
    assert_raised_because(einfo, plan, PN.equal)
    wa.check(no_change = True)

    # Renaming will succeed if we skip the offending paths.
    wa = create_wa(origs, news)
    plan = RenamingPlan(
        inputs = wa.origs + wa.news,
        controls = 'skip-equal',
    )
    plan.rename_paths()
    wa.check()

def test_missing_orig(tr, create_wa):
    # Paths.
    origs = ('a', 'b')
    news = ('a1', 'b1')
    missing_origs = ('c', 'd')
    missing_news = ('c1', 'd1')

    # Helper to assemble RenamingPlan inputs.
    # We need to includes missing_news so there are equal N of
    # origs and news given as arguments to RenamingPlan.
    def assemble_inputs(wa):
        return wa.origs + missing_origs + wa.news + missing_news

    # Renaming plan where some of origs are missing.
    # Prepare will not raise, but will mark the plan as failed.
    # Rename attempt will raise.
    wa = create_wa(origs, news, rootless = True)
    plan = RenamingPlan(
        inputs = assemble_inputs(wa),
    )
    plan.prepare()
    assert plan.failed
    with pytest.raises(MvsError) as einfo:
        with wa.cd():
            plan.rename_paths()
    assert_raised_because(einfo, plan, PN.missing)
    wa.check(no_change = True)

    # Renaming will succeed if we skip the offending paths.
    wa = create_wa(origs, news, rootless = True)
    plan = RenamingPlan(
        inputs = assemble_inputs(wa),
        controls = 'skip-missing',
    )
    with wa.cd():
        plan.rename_paths()
    wa.check()

def test_new_exists(tr, create_wa):
    # Some paths where one of the news will be in extras
    # and thus will exist before renaming.
    origs = ('a', 'b', 'c')
    news = ('a1', 'b1', 'c1')
    extras = ('a1',)
    expecteds_skip = ('a', 'a1', 'b1', 'c1')
    expecteds_clobber = news

    # Scenario: one of new paths exists.
    # Prepare will mark plan as failed. Rename will raise.
    wa = create_wa(origs, news, extras)
    plan = RenamingPlan(
        inputs = wa.origs + wa.news,
    )
    plan.prepare()
    assert plan.failed
    with pytest.raises(MvsError) as einfo:
        plan.rename_paths()
    assert_raised_because(einfo, plan, PN.existing)
    wa.check(no_change = True)

    # Renaming will succeed if we skip the offending paths.
    wa = create_wa(origs, news, extras, expecteds_skip)
    plan = RenamingPlan(
        inputs = wa.origs + wa.news,
        controls = 'skip-existing',
    )
    plan.rename_paths()
    wa.check()

    # Renaming will succeed if we clobber the offending paths.
    wa = create_wa(origs, news, extras, expecteds_clobber)
    plan = RenamingPlan(
        inputs = wa.origs + wa.news,
        controls = 'clobber-existing',
    )
    plan.rename_paths()
    wa.check()

def test_new_parent_missing(tr, create_wa):
    # Paths where a parent of a new path will be missing.
    origs = ('a', 'b', 'c')
    news = ('a1', 'b1', 'xy/zzz/c1')
    expecteds_skip = ('a1', 'b1', 'c')
    expecteds_create = news + ('xy/', 'xy/zzz/')

    # Prepare will mark plan as failed. Rename will raise.
    wa = create_wa(origs, news)
    plan = RenamingPlan(
        inputs = wa.origs + wa.news,
    )
    plan.prepare()
    assert plan.failed
    with pytest.raises(MvsError) as einfo:
        plan.rename_paths()
    assert_raised_because(einfo, plan, PN.parent)
    wa.check(no_change = True)

    # Renaming will succeed if we skip the offending paths.
    wa = create_wa(origs, news, (), expecteds_skip)
    plan = RenamingPlan(
        inputs = wa.origs + wa.news,
        controls = 'skip-parent',
    )
    plan.rename_paths()
    wa.check()

    # Renaming will succeed if we create the missing parents.
    wa = create_wa(origs, news, (), expecteds_create)
    plan = RenamingPlan(
        inputs = wa.origs + wa.news,
        controls = 'create-parent',
    )
    plan.rename_paths()
    wa.check()

def test_news_collide(tr, create_wa):
    # Paths where some of the new paths collide.
    origs = ('a', 'b', 'c')
    news = ('a1', 'b1', 'a1')
    expecteds_skip = ('a', 'b1', 'c')
    expecteds_clobber = ('a1', 'b1')

    # Prepare will mark plan as failed. Rename will raise.
    wa = create_wa(origs, news)
    plan = RenamingPlan(
        inputs = wa.origs + wa.news,
    )
    plan.prepare()
    assert plan.failed
    with pytest.raises(MvsError) as einfo:
        plan.rename_paths()
    assert_raised_because(einfo, plan, PN.colliding)
    wa.check(no_change = True)

    # Renaming will succeed if we skip the offending paths.
    wa = create_wa(origs, news, (), expecteds_skip)
    plan = RenamingPlan(
        inputs = wa.origs + wa.news,
        controls = 'skip-colliding',
    )
    plan.rename_paths()
    wa.check()

    # Renaming will succeed if we allow clobbering.
    wa = create_wa(origs, news, (), expecteds_clobber)
    plan = RenamingPlan(
        inputs = wa.origs + wa.news,
        controls = 'clobber-colliding',
    )
    plan.rename_paths()
    wa.check()

def test_failures_skip_all(tr, create_wa):
    # Paths where all new paths collide.
    origs = ('a', 'b', 'c')
    news = ('Z', 'Z', 'Z')

    # Renaming will raise because the skip control
    # will filter out all paths.
    wa = create_wa(origs, news)
    plan = RenamingPlan(
        inputs = wa.origs + wa.news,
        controls = 'skip-colliding',
    )
    plan.prepare()
    assert plan.failed
    with pytest.raises(MvsError) as einfo:
        plan.rename_paths()
    assert_raised_because(einfo, plan, PN.all_filtered)
    wa.check(no_change = True)

