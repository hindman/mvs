'''

Tests to be refactored:
    x test_top_level_imports
    x test_no_inputs
    x test_structure_default
    x test_structure_paragraphs
    x test_structure_pairs
    x test_structure_rows
    x test_renaming_code
    x test_filtering_code
    x test_code_compilation_fails
    x test_code_execution_fails
    x test_seq
    x test_common_prefix
    x test_plan_as_dict
    x test_prepare_rename_multiple_times
    x test_invalid_controls
    x test_equal
    - test_missing_orig
    - test_orig_type
    - test_new_exists
    - test_new_exists_different_case
    - test_new_exists_non_empty
    - test_new_parent_missing
    - test_news_collide
    - test_failures_skip_all

'''


import pytest
from itertools import chain

# Top-level package imports.
from mvs import RenamingPlan, MvsError, __version__

# Imports for testing.
from mvs.utils import (
    CON,
    FS_TYPES,
    MSG_FORMATS as MF,
    STRUCTURES,
    file_system_case_sensitivity,
)

from mvs.problems import (
    CONTROLLABLES,
    CONTROLS,
    PROBLEM_NAMES as PN,
    Problem,
)

####
# A mega-helper to perform common checks.
# Used by most tests.
####

def run_checks(
               # Fixtures.
               tr,
               create_wa,
               # WorkArea.
               origs,
               news,
               extras = None,
               expecteds = None,
               rootless = False,
               # RenamingPlan.
               inputs = None,
               include_origs = True,
               include_news = True,
               include_extras = True,
               # Assertion making.
               early_checks = None,
               check_wa = True,
               failure = False,
               no_change = False,
               reason = None,
               # Renaming behavior.
               prepare_only = False,
               prepare_before = 0,
               **plan_kws):

    # Set up WorkArea.
    wa = create_wa(
        origs,
        news,
        extras = extras,
        expecteds = expecteds,
        rootless = rootless
    )

    # Set up RenamingPlan.
    if inputs is None:
        inputs = (
            (wa.origs if include_origs else ()) +
            (wa.news if include_news else ()) +
            (wa.extras if include_extras else ())
        )
    plan = RenamingPlan(inputs, **plan_kws)

    # Let caller make early assertions.
    if early_checks:
        early_checks(wa, plan)

    # Helper to execute plan.prepare() and plan.rename_paths().
    def do_rename():
        if rootless:
            with wa.cd():
                for _ in range(prepare_before):
                    plan.prepare()
                plan.rename_paths()
        else:
            for _ in range(prepare_before):
                plan.prepare()
            plan.rename_paths()

    # Run the renaming or just the preparations.
    # Check for failure and, in some case, its reason.
    if prepare_only:
        no_change = True
        plan.prepare()
        if failure:
            assert plan.failed
    elif failure:
        plan.prepare()
        assert plan.failed
        with pytest.raises(MvsError) as einfo:
            do_rename()
        if reason:
            assert_raised_because(einfo, plan, reason)
    else:
        do_rename()
        assert not plan.failed

    # Check work area.
    if check_wa:
        wa.check(no_change = no_change)

    # Let the caller make other custom assertions.
    return (wa, plan)

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

def test_no_inputs(tr, create_wa):
    # Paths and args.
    origs = ('a', 'b')
    news = ('aa', 'bb')
    run_args = (tr, create_wa, origs, news)

    # If given no inputs, renaming will be rejected.
    wa, plan = run_checks(
        *run_args,
        inputs = (),
        failure = True,
        reason = PN.parsing_no_paths,
        no_change = True,
    )

def test_structure_default(tr, create_wa):
    # Paths and args.
    origs = ('a', 'b', 'c')
    news = ('a.new', 'b.new', 'c.new')
    run_args = (tr, create_wa, origs, news)

    # A RenamingPlan defaults to flat input structure,
    # or the user can request flat explicitly.
    for s in (None, STRUCTURES.flat):
        wa, plan = run_checks(
            *run_args,
            structure = s,
        )
        assert plan.structure == STRUCTURES.flat

def test_structure_paragraphs(tr, create_wa):
    # Paths and args.
    origs = ('a', 'b', 'c')
    news = ('a.new', 'b.new', 'c.new')
    run_args = (tr, create_wa, origs, news)

    # Create a WorkArea to be used by assemble_inputs()
    # to create input paths.
    WA = create_wa(origs, news)

    # Helper to create variations of the --paragraphs inputs structure.
    def assemble_inputs(n = 1, before = False, after = False, split_news = False):
        # Set up empty lines to be included.
        EMPTIES = ('', '')
        before = EMPTIES if before else ()
        between = EMPTIES[0:n]
        after = EMPTIES if after else ()
        # Provide the new paths either in one paragraph or two.
        if split_news:
            news1 = WA.news[0:1]
            news2 = WA.news[1:]
        else:
            news1 = WA.news
            news2 = ()
        # Return the input paths.
        return before + WA.origs + between + news1 + after + news2

    # Scenarios: varying N of empty lines between origs and news,
    # optionally with empty lines before and after.
    assemble_kws = (
        dict(n = 1),
        dict(n = 2),
        dict(n = 1, before = True),
        dict(n = 2, after = True),
        dict(n = 1, before = True, after = True),
    )
    for kws in assemble_kws:
        wa, plan = run_checks(
            *run_args,
            inputs = assemble_inputs(**kws),
            structure = STRUCTURES.paragraphs,
        )

    # Two scenarios where renaming should be rejects:
    # (1) no blank lines between paragraphs, and
    # (2) three paragraphs rather than two.
    assemble_kws = (
        dict(n = 0),
        dict(n = 1, after = True, split_news = True),
    )
    for kws in assemble_kws:
        wa, plan = run_checks(
            *run_args,
            inputs = assemble_inputs(**kws),
            structure = STRUCTURES.paragraphs,
            failure = True,
            reason = PN.parsing_paragraphs,
            no_change = True,
        )

def test_structure_pairs(tr, create_wa):
    # Paths and args.
    origs = ('a', 'b', 'c')
    news = ('a.new', 'b.new', 'c.new')
    run_args = (tr, create_wa, origs, news)

    # Create a WorkArea to be used by assemble_inputs()
    # to create input paths.
    WA = create_wa(origs, news)

    # Helper to create variations of the --pairs inputs structure.
    def assemble_inputs(include_empties = False):
        if include_empties:
            empties = ('',) * len(WA.origs)
            zipped = zip(WA.origs, WA.news, empties)
        else:
            zipped = zip(WA.origs, WA.news)
        return tuple(chain(*zipped))

    # Scenario: inputs as orig-new pairs.
    wa, plan = run_checks(
        *run_args,
        inputs = assemble_inputs(),
        structure = STRUCTURES.pairs,
    )

    # Scenario: same thing, but with some empty lines thrown in.
    wa, plan = run_checks(
        *run_args,
        inputs = assemble_inputs(include_empties = True),
        structure = STRUCTURES.pairs,
    )

    # Scenario: an odd number of inputs. Renaming should be rejected.
    wa, plan = run_checks(
        *run_args,
        inputs = assemble_inputs()[0:-1],
        structure = STRUCTURES.pairs,
        failure = True,
        no_change = True,
        reason = PN.parsing_imbalance,
    )

def test_structure_rows(tr, create_wa):
    # Paths and args.
    origs = ('a', 'b', 'c')
    news = ('a.new', 'b.new', 'c.new')
    run_args = (tr, create_wa, origs, news)

    # Create a WorkArea to be used by assemble_inputs()
    # to create input paths.
    WA = create_wa(origs, news)

    # Helper to create variations of the --rows inputs structure.
    def assemble_inputs(fmt = None):
        fmt = fmt or '{}\t{}'
        EMPTY = ('', '')
        inputs = tuple(
            fmt.format(o, n)
            for o, n in  zip(WA.origs, WA.news)
        )
        return EMPTY + inputs[0:2] + EMPTY + inputs[2:] + EMPTY

    # Scenario: inputs as orig-new rows.
    wa, plan = run_checks(
        *run_args,
        inputs = assemble_inputs(),
        structure = STRUCTURES.rows,
    )

    # Scenarios with invalid row formats: empty cells, odd number
    # of cells, or both. Renaming should be rejected.
    BAD_FORMATS = (
        '{}\t',
        '{}\t\t{}',
        '{}\t{}\t',
        '\t{}\t{}',
    )
    for fmt in BAD_FORMATS:
        wa, plan = run_checks(
            *run_args,
            inputs = assemble_inputs(fmt),
            structure = STRUCTURES.rows,
            failure = True,
            no_change = True,
            reason = PN.parsing_row,
        )

####
# User-supplied code.
####

def test_renaming_code(tr, create_wa):
    # Paths and args.
    origs = ('a', 'b', 'c')
    news = ('aa', 'bb', 'cc')
    run_args = (tr, create_wa, origs, news)

    # Renaming code in three forms.
    code_str = 'return o + o'
    code_lambda = lambda o, p, seq, plan: o + o
    def code_func(o, p, seq, plan): return o + o

    # Scenarios: generate new-paths via user-supplied code.
    for code in (code_str, code_lambda, code_func):
        wa, plan = run_checks(
            *run_args,
            inputs = origs,
            rename_code = code,
            rootless = True,
        )

def test_filtering_code(tr, create_wa):
    # Paths and args.
    origs = ('a', 'b', 'c')
    news = ('aa', 'bb', 'cc')
    extras = ('d', 'dd', 'xyz/')
    run_args = (tr, create_wa, origs, news)

    # Scenario: provide orig and extras as inputs, and
    # then use filtering code to filter out the extras.
    wa, plan = run_checks(
        *run_args,
        extras = extras,
        include_news = False,
        include_extras = True,
        rename_code = 'return o + o',
        filter_code = 'return not ("d" in o or p.is_dir())',
        rootless = True,
    )

def test_code_compilation_fails(tr, create_wa):
    # Paths and args.
    origs = ('a', 'b', 'c')
    news = ('aa', 'bb', 'cc')
    run_args = (tr, create_wa, origs, news)

    # Some bad code to use for renaming and filtering.
    BAD_CODE = 'FUBB BLORT'

    # Helper to check some details about the first uncontrolled Problem.
    def check_problem(plan):
        prob = plan.uncontrolled_problems[0]
        assert BAD_CODE in prob.msg
        assert 'invalid syntax' in prob.msg

    # Scenario: invalid renaming code.
    wa, plan = run_checks(
        *run_args,
        include_news = False,
        rename_code = BAD_CODE,
        failure = True,
        no_change = True,
        reason = PN.user_code_exec,
    )
    check_problem(plan)

    # Scenario: invalid filtering code.
    wa, plan = run_checks(
        *run_args,
        filter_code = BAD_CODE,
        failure = True,
        no_change = True,
        reason = PN.user_code_exec,
    )
    check_problem(plan)

def test_code_execution_fails(tr, create_wa):
    # Paths and args.
    FAILING_ORIG = 'b'
    origs = ('a', FAILING_ORIG, 'c')
    news = ('aa', 'bb', 'cc')
    run_args = (tr, create_wa, origs, news)

    # Code that will cause the second RenamePair
    # to fail during execution of user code.
    rename_code1 = 'return FUBB if seq == 2 else o + o'
    rename_code2 = 'return 9999 if seq == 2 else o + o'
    filter_code = 'return FUBB if seq == 2 else True'

    # Three scenarios that will cause renaming to be rejected:
    # - Renaming code raises an exception.
    # - Renaming code returns bad data type.
    # - Filtering code raises an exception.
    scenarios = (
        dict(rename_code = rename_code1, reason = PN.rename_code_invalid),
        dict(rename_code = rename_code2, reason = PN.rename_code_bad_return),
        dict(filter_code = filter_code, reason = PN.filter_code_invalid),
    )
    for kws in scenarios:
        wa, plan = run_checks(
            *run_args,
            rootless = True,
            failure = True,
            no_change = True,
            include_news = 'filter_code' in kws,
            **kws,
        )
        probs = plan.uncontrolled_problems
        assert len(probs) == 1
        p = probs[0]
        assert p.rp.orig == FAILING_ORIG
        assert p.name == kws['reason']

def test_seq(tr, create_wa):
    # Paths and args.
    origs = ('a', 'b', 'c')
    news = ('a.20', 'b.30', 'c.40')
    run_args = (tr, create_wa, origs, news)

    # Scenario: user defines a sequence and uses
    # its values in user-supplied code.
    wa, plan = run_checks(
        *run_args,
        rootless = True,
        include_news = False,
        rename_code = 'return f"{o}.{seq * 2}"',
        seq_start = 10,
        seq_step = 5,
    )

def test_common_prefix(tr, create_wa):
    # Paths and args.
    origs = ('blah-a', 'blah-b', 'blah-c')
    news = ('a', 'b', 'c')
    run_args = (tr, create_wa, origs, news)

    # User-supplied code exercises strip_prefix() helper.
    wa, plan = run_checks(
        *run_args,
        rootless = True,
        include_news = False,
        rename_code = 'return plan.strip_prefix(o)',
    )

####
# RenamingPlan data.
####

def test_plan_as_dict(tr, create_wa):
    # Paths and args.
    origs = ('a', 'b', 'c')
    news = ('a.10', 'b.15', 'c.20')
    run_args = (tr, create_wa, origs, news)

    # Helper to check keys in plan.as_dict.
    def check_plan_dict(wa, plan):
        assert sorted(plan.as_dict) == sorted((
            'inputs',
            'structure',
            'rename_code',
            'filter_code',
            'indent',
            'seq_start',
            'seq_step',
            'controls',
            'problems',
            'prefix_len',
            'rename_pairs',
            'tracking_index',
        ))

    # Define a RenamingPlan. Check its as_dict keys
    # both before and after renaming.
    wa, plan = run_checks(
        *run_args,
        rootless = True,
        include_news = False,
        rename_code = 'return f"{o}.{seq}"',
        filter_code = 'return "d" not in o',
        seq_start = 10,
        seq_step = 5,
        early_checks = check_plan_dict,
    )
    check_plan_dict(wa, plan)

####
# Check unexpected usage scenarios.
####

def test_prepare_rename_multiple_times(tr, create_wa):
    # Paths and args.
    origs = ('a', 'b', 'c')
    news = ('aa', 'bb', 'cc')
    run_args = (tr, create_wa, origs, news)

    # Scenario: can call plan.prepare() multiple times
    # without causing any trouble: renaming succeeds.
    wa, plan = run_checks(
        *run_args,
        rootless = True,
        include_news = False,
        rename_code = 'return o + o',
        prepare_before = 3,
    )

    # But if you try to call plan.rename_paths() a
    # second time, an exception is raised and the work
    # area won't be affected.
    with pytest.raises(MvsError) as einfo:
        plan.rename_paths()
    assert einfo.value.params['msg'] == MF.rename_done_already
    wa.check()

####
# Problems and problem-control.
####

def test_invalid_controls(tr, create_wa):
    # Paths and args.
    origs = ('a', 'b', 'c')
    news = ('a.new', 'b.new', 'c.new')
    run_args = (tr, create_wa, origs, news)

    # Base scenario: it works fine.
    # In addition, we will re-use the inputs defined here
    # in subsequent tests, which don't need a WorkArea
    # because the RenamingPlan will raise during initialization.
    wa, plan = run_checks(*run_args)
    INPUTS = plan.inputs

    # Scenarios: can configure problem-control in various ways.
    all_controls = CONTROLLABLES[CONTROLS.skip]
    checks = (
        ('all', all_controls),
        ('first2', all_controls[0:2]),
    )
    for label, controls in checks:
        tup = tuple(f'skip-{c}' for c in controls)
        plan1 = RenamingPlan(INPUTS, controls = tup)
        plan2 = RenamingPlan(INPUTS, controls = ' '.join(tup))
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
            plan = RenamingPlan(INPUTS, controls = tup)
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
            plan = RenamingPlan(INPUTS, controls = pc_name)
        msg = einfo.value.params['msg']
        exp = MF.invalid_control.format(pc_name)
        assert msg == exp

def test_equal(tr, create_wa):
    # Paths and args.
    # One of the origs equals its new counterpart.
    SAME = ('d',)
    origs = ('a', 'b', 'c') + SAME
    news = ('a.new', 'b.new', 'c.new') + SAME
    run_args = (tr, create_wa, origs, news)

    # Scenario: renaming will succeed, because
    # skip-equal is a default control.
    wa, plan = run_checks(*run_args)
    wa, plan = run_checks(*run_args, controls = 'skip-equal')

    # Scenario: but renaming will be rejected
    # if we cancel the default.
    wa, plan = run_checks(
        *run_args,
        controls = '',
        failure = True,
        no_change = True,
        reason = PN.equal,
    )

def test_missing_orig(tr, create_wa):
    # Paths.
    origs = ('a', 'b')
    news = ('a.new', 'b.new')
    missing_origs = ('c', 'd')
    missing_news = ('c.new', 'd.new')

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

def test_orig_type(tr, create_wa):
    # Paths, including one symlink.
    target = 'c.target'
    origs = ('a', 'b', f'c::{target}')
    news = ('a.new', 'b.new', 'c.new')
    extras = (target,)

    # Renaming will be rejected if any of the origs are not
    # regular files or directories.
    wa = create_wa(origs, news, extras = extras)
    plan = RenamingPlan(
        inputs = wa.origs + wa.news,
    )
    plan.prepare()
    assert plan.failed
    with pytest.raises(MvsError) as einfo:
        plan.rename_paths()
    assert_raised_because(einfo, plan, PN.type)
    wa.check(no_change = True)

def test_new_exists(tr, create_wa):
    # Some paths where one of the news will be in extras
    # and thus will exist before renaming.
    origs = ('a', 'b', 'c')
    news = ('a.new', 'b.new', 'c.new')
    extras = ('a.new',)
    extras_diff = ('a.new/',)
    expecteds_skip = ('a', 'a.new', 'b.new', 'c.new')
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

    # But we cannot clobber if the victim is of a different type.
    wa = create_wa(origs, news, extras_diff)
    plan = RenamingPlan(
        inputs = wa.origs + wa.news,
        controls = 'clobber-existing',
    )
    plan.prepare()
    assert plan.failed
    with pytest.raises(MvsError) as einfo:
        plan.rename_paths()
    assert_raised_because(einfo, plan, PN.existing_diff)
    wa.check(no_change = True)

def test_new_exists_different_case(tr, create_wa):
    # Paths where a pre-exising path is a
    # differently-cased variation of a new path.
    origs = ('a',)
    news = ('b',)
    extras = ('B',)
    expecteds_clobber = extras

    # Scenario: a pre-existing path is a
    # differently-cased variation of a new path.
    wa = create_wa(origs, news, extras)
    plan = RenamingPlan(
        inputs = wa.origs + wa.news,
    )
    plan.prepare()
    if file_system_case_sensitivity() == FS_TYPES.case_sensitive:
        # On a case-sensitive system, renaming should succeed.
        plan.rename_paths()
        wa.check()
    else:
        # On a non-case-sensitive system, renaming should be rejected.
        assert plan.failed
        with pytest.raises(MvsError) as einfo:
            plan.rename_paths()
        assert_raised_because(einfo, plan, PN.existing)
        wa.check(no_change = True)

        # But if well request clobbering, we expect renaming
        # to occur and for the paths to end up with the desired casing.
        #
        # TODO: currently, we don't end up with desired casing.
        # Instead, we end up with case-preservation.
        wa = create_wa(origs, news, extras, expecteds_clobber)
        plan = RenamingPlan(
            inputs = wa.origs + wa.news,
            controls = 'clobber-existing',
        )
        plan.rename_paths()
        wa.check()

def test_new_exists_non_empty(tr, create_wa):
    # But we cannot clobber if the victim is of a different type.
    origs = ('a/', 'b', 'c')
    news = ('a.new', 'b.new', 'c.new')
    extras = ('a.new/', 'a.new/foo')

    # Basic scenario: its works.
    wa = create_wa(origs, news)
    plan = RenamingPlan(
        inputs = wa.origs + wa.news,
    )
    plan.rename_paths()
    wa.check()

    # Scenario: but if one of the new paths exists, it will fail.
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

    # Scenario: and it won't help to ask for clobbering because
    # the victim is a non-empty directory.
    # TODO
    # ...
    return
    wa = create_wa(origs, news, extras)
    plan = RenamingPlan(
        inputs = wa.origs + wa.news,
        controls = 'clobber-existing',
    )
    plan.prepare()
    assert plan.failed
    with pytest.raises(MvsError) as einfo:
        plan.rename_paths()
    assert_raised_because(einfo, plan, PN.existing_full)
    wa.check(no_change = True)

def test_new_parent_missing(tr, create_wa):
    # Paths where a parent of a new path will be missing.
    origs = ('a', 'b', 'c')
    news = ('a.new', 'b.new', 'xy/zzz/c.new')
    expecteds_skip = ('a.new', 'b.new', 'c')
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
    news = ('a.new', 'b.new', 'a.new')
    expecteds_skip = ('a', 'b.new', 'c')
    expecteds_clobber = ('a.new', 'b.new')
    origs_diff = ('a', 'b', 'c/')

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

    # But clobbering among news cannot involve different file types.
    wa = create_wa(origs_diff, news)
    plan = RenamingPlan(
        inputs = wa.origs + wa.news,
    )
    plan.prepare()
    assert plan.failed
    with pytest.raises(MvsError) as einfo:
        plan.rename_paths()
    assert_raised_because(einfo, plan, PN.colliding_diff)
    wa.check(no_change = True)

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

