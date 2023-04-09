import pytest
from itertools import chain
from pathlib import Path

from mvs.plan import RenamingPlan, Renaming

from mvs.utils import (
    CON,
    FAILURE_NAMES as FN,
    FAILURE_VARIETIES as FV,
    FS_TYPES,
    Failure,
    MSG_FORMATS as MF,
    MvsError,
    PROBLEM_NAMES as PN,
    PROBLEM_VARIETIES as PV,
    Problem,
    STRUCTURES,
    case_sensitivity,
)

####
# A mega-helper to perform common checks. Used by most tests.
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
               include_extras = False,
               # Assertion making.
               early_checks = None,
               diagnostics = False,
               inventory = None,
               check_wa = True,
               check_failure = True,
               failure = False,
               no_change = False,
               reason = None,
               return_einfo = False,
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
    def do_prepare_and_rename():
        # Prepare.
        n_preps = int(prepare_before or prepare_only or diagnostics)
        for _ in range(n_preps):
            plan.prepare()
        if prepare_only:
            return None

        # Print diagnostic info.
        if diagnostics:
            run_diagnostics(tr, wa, plan)

        # Rename.
        if failure:
            with pytest.raises(MvsError) as einfo:
                plan.rename_paths()
            return einfo
        else:
            plan.rename_paths()
            return None

    # Run the preparation and renaming.
    if rootless:
        with wa.cd():
            einfo = do_prepare_and_rename()
    else:
        einfo = do_prepare_and_rename()

    # Check for plan failure and its reason.
    if check_failure:
        if failure:
            assert plan.failed
            if reason:
                assert isinstance(reason, Failure) # TODO: remove.
                assert einfo.value.params['msg'] == MF.prepare_failed
                f = plan.failure
                assert f
                got = (f.name, f.variety)
                exp = (reason.name, reason.variety)
                assert got == exp
        else:
            assert not plan.failed

    # Check work area.
    if check_wa:
        if prepare_only:
            no_change = True
        wa.check(no_change = no_change)

    # Check the plan's inventory of Renaming instances.
    if inventory is not False:
        # Assemble the expected inventory. The parmeter
        # can be dict, None, or str.
        if isinstance(inventory, dict):
            # Dict provides the rn.orig values directly.
            exp = {
                attr : sorted(inventory.get(attr, []))
                for attr in INV_MAP.values()
            }
        else:
            # A str or None uses a convenience format based on INV_MAP.
            n = len(wa.origs)
            if inventory is None:
                inventory = '.'
            if len(inventory) == 1:
                inventory = inventory * n
            assert len(inventory) == n
            pairs = tuple(zip(inventory, wa.origs))
            exp = {
                attr : sorted(o for i, o in pairs if i == k)
                for k, attr in INV_MAP.items()
            }
        # Assemble actual inventory and assert.
        got = {
            attr : sorted(rn.orig for rn in getattr(plan, attr))
            for attr in INV_MAP.values()
        }
        assert got == exp

    # Let the caller make other custom assertions.
    if return_einfo:
        return (wa, plan, einfo)
    else:
        return (wa, plan)

# Helper used to print the WorkArea and RenamingPlan data as JSON.
def run_diagnostics(tr, wa, plan):
    tr.dumpj(wa.as_dict, 'WorkArea')
    tr.dumpj(plan.as_dict, 'RenamingPlan')

# Convenience scheme for the inventory parameter in run_checks().
EMPTY = '_'
INV_MAP = {
    '.': 'active',
    'f': 'filtered',
    's': 'skipped',
    'E': 'excluded',
}

####
# Inputs and their structures.
####

def test_no_inputs(tr, create_wa):
    # Paths and args.
    origs = ('a', 'b')
    news = ('aa', 'bb')
    rename_code = 'return o + o'
    run_args = (tr, create_wa, origs, news)

    # Scenario: if given no inputs, renaming will be rejected.
    # We run the scenario with and without rename_code just
    # to exercise an additional code path.
    for code in (None, rename_code):
        wa, plan = run_checks(
            *run_args,
            inputs = (),
            rename_code = code,
            failure = True,
            reason = Failure(FN.parsing, variety = FV.no_paths),
            no_change = True,
            inventory = EMPTY,
        )

@pytest.mark.skip(reason = 'overhaul')
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

@pytest.mark.skip(reason = 'overhaul')
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
            reason = FN.parsing_paragraphs,
            no_change = True,
            inventory = EMPTY,
        )

@pytest.mark.skip(reason = 'overhaul')
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
        reason = FN.parsing_imbalance,
        inventory = EMPTY,
    )

@pytest.mark.skip(reason = 'overhaul')
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
            reason = FN.parsing_row,
            inventory = EMPTY,
        )

####
# User-supplied code.
####

@pytest.mark.skip(reason = 'overhaul')
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

@pytest.mark.skip(reason = 'overhaul')
def test_filtering_code(tr, create_wa):
    # Paths and args.
    origs = ('a', 'b', 'c')
    news = ('aa', 'bb', 'cc')
    extras = ('d', 'dd', 'xyz/')
    run_args = (tr, create_wa, origs, news)
    exp_inv = dict(
        active = ['a', 'b', 'c'],
        filtered = ['d', 'dd', 'xyz'],
    )

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
        inventory = exp_inv,
    )

@pytest.mark.skip(reason = 'overhaul')
def test_code_compilation_fails(tr, create_wa):
    # Paths and args.
    origs = ('a', 'b', 'c')
    news = ('aa', 'bb', 'cc')
    run_args = (tr, create_wa, origs, news)

    # Some bad code to use for renaming and filtering.
    BAD_CODE = 'FUBB BLORT'

    # Helper to check some details about the first uncontrolled Problem.
    def check_fail(plan):
        f = plan.failures[0]
        assert BAD_CODE in f.msg
        assert 'invalid syntax' in f.msg

    # Scenario: invalid renaming code.
    wa, plan = run_checks(
        *run_args,
        include_news = False,
        rename_code = BAD_CODE,
        failure = True,
        no_change = True,
        reason = FN.user_code_exec,
    )
    check_fail(plan)

    # Scenario: invalid filtering code.
    wa, plan = run_checks(
        *run_args,
        filter_code = BAD_CODE,
        failure = True,
        no_change = True,
        reason = FN.user_code_exec,
    )
    check_fail(plan)

@pytest.mark.skip(reason = 'overhaul')
def test_code_execution_fails(tr, create_wa):
    # Paths and args.
    FAILING_ORIG = 'b'
    origs = ('a', FAILING_ORIG, 'c')
    news = ('aa', 'bb', 'cc')
    expecteds_skip = ('aa', FAILING_ORIG, 'cc')
    exp_inv = '.s.'
    exp_invH = exp_inv.replace('s', 'E')
    run_args = (tr, create_wa, origs, news)

    # Code that will cause the second Renaming
    # to fail during execution of user code.
    rename_code1 = 'return FUBB if seq == 2 else o + o'
    rename_code2 = 'return 9999 if seq == 2 else o + o'
    filter_code = 'return FUBB if seq == 2 else True'

    # Three scenarios:
    # - Renaming code raises an exception.
    # - Renaming code returns bad data type.
    # - Filtering code raises an exception.
    scenarios = (
        dict(rename_code = rename_code1, reason = PN.rename),
        dict(rename_code = rename_code2, reason = PN.rename),
        dict(filter_code = filter_code, reason = PN.filter),
    )

    # By default, user-code failures halt the renaming plan.
    for kws in scenarios:
        wa, plan = run_checks(
            *run_args,
            rootless = True,
            failure = True,
            no_change = True,
            include_news = 'filter_code' in kws,
            inventory = exp_invH,
            **kws,
        )

    # Or the user can skip renamings with such problems.
    for kws in scenarios:
        wa, plan = run_checks(
            *run_args,
            controls = 'skip-filter skip-rename',
            rootless = True,
            include_news = 'filter_code' in kws,
            expecteds = expecteds_skip,
            inventory = exp_inv,
            **kws,
        )

@pytest.mark.skip(reason = 'overhaul')
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

@pytest.mark.skip(reason = 'overhaul')
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

@pytest.mark.skip(reason = 'overhaul')
def test_plan_as_dict(tr, create_wa):
    # Paths and args.
    origs = ('a', 'b', 'c')
    news = ('a.10', 'b.15', 'c.20')
    run_args = (tr, create_wa, origs, news)
    filter_code = lambda o, p, seq, plan: 'd' not in o

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
            'strict',
            'renamings',
            'filtered',
            'skipped',
            'excluded',
            'failures',
            'prefix_len',
            'tracking_index',
        ))

    # Define a RenamingPlan. Check its as_dict keys
    # both before and after renaming.
    wa, plan = run_checks(
        *run_args,
        rootless = True,
        include_news = False,
        rename_code = 'return f"{o}.{seq}"',
        filter_code = filter_code,
        seq_start = 10,
        seq_step = 5,
        early_checks = check_plan_dict,
    )
    check_plan_dict(wa, plan)

####
# Check unexpected usage scenarios.
####

@pytest.mark.skip(reason = 'overhaul')
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

@pytest.mark.skip(reason = 'overhaul')
def test_controls(tr, create_wa):
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

    # But we cannot control the same problem in two different ways.
    checks = (
        (PN.parent, CONTROLS.skip, CONTROLS.create),
        (PN.exists, CONTROLS.skip, CONTROLS.clobber),
        (PN.collides, CONTROLS.skip, CONTROLS.clobber),
    )
    for prob, *controls in checks:
        tup = tuple(f'{c}-{prob}' for c in controls)
        with pytest.raises(MvsError) as einfo:
            plan = RenamingPlan(INPUTS, controls = tup)
        msg = einfo.value.params['msg']
        exp = MF.conflicting_controls.format(prob, *controls)
        assert msg == exp

    # And we cannot control a problem in an inappropriate way.
    checks = (
        (PN.equal, CONTROLS.clobber),
        (PN.missing, CONTROLS.create),
        (PN.parent, CONTROLS.clobber),
    )
    for prob, control in checks:
        pc_name = f'{control}-{prob}'
        with pytest.raises(MvsError) as einfo:
            plan = RenamingPlan(INPUTS, controls = pc_name)
        msg = einfo.value.params['msg']
        exp = MF.invalid_control.format(pc_name)
        assert msg == exp

    # Or in a completely invalid way.
    BAD_VAL = 999
    with pytest.raises(MvsError) as einfo:
        plan = RenamingPlan(INPUTS, controls = BAD_VAL)
    err = einfo.value
    assert err.msg == MF.invalid_controls
    assert err.params['controls'] == BAD_VAL

def test_equal(tr, create_wa):
    # Paths and args.
    SAME = 'd'
    origs = ('a', 'b', 'c') + (SAME,)
    news = ('a.new', 'b.new', 'c.new') + (SAME,)
    exp_inv = '...E'
    strict = 'excluded'
    reason = Failure(FN.strict, strict)
    run_args = (tr, create_wa, origs, news)

    # Scenario: one of the orig paths equals its new counterpart.
    # By default, the offending Renaming will be excluded.
    wa, plan = run_checks(
        *run_args,
        inventory = exp_inv,
    )

    # But in strict mode the plan will fail.
    wa, plan = run_checks(
        *run_args,
        strict = strict,
        failure = True,
        no_change = True,
        reason = reason,
        inventory = exp_inv,
    )

@pytest.mark.skip(reason = 'overhaul')
def test_same(tr, create_wa):
    # Paths and args.
    origs = ('foo/xyz', 'BAR/xyz', 'a')
    news = ('FOO/xyz', 'bar/xyz', 'a.new')
    expecteds_no_create = ('foo', 'foo/xyz', 'BAR', 'BAR/xyz', 'a')
    expecteds_create = ('foo', 'FOO', 'FOO/xyz', 'BAR', 'bar', 'bar/xyz', 'a.new')
    expecteds_skip = ('foo', 'foo/xyz', 'BAR', 'BAR/xyz', 'a.new')
    expecteds_no_skip = origs + ('foo', 'BAR')
    exp_inv = 'ss.'
    exp_invH = exp_inv.replace('s', 'E')
    run_args = (tr, create_wa, origs, news)

    # Scenarios: for the first two Renaming instances,
    # orig and new differ only in the casing of their parent.
    if case_sensitivity() == FS_TYPES.case_sensitive:
        # Scenario: case-sensitive system: by default, renamings
        # without new-parents will be skipped.
        wa, plan = run_checks(
            *run_args,
            expecteds = expecteds_skip,
            inventory = exp_inv,
        )

        # Scenario: it will be rejected if we set the control to halt.
        wa, plan = run_checks(
            *run_args,
            expecteds = expecteds_no_create,
            controls = 'halt-parent',
            failure = True,
            reason = PN.parent,
            inventory = exp_invH,
        )

        # Scenario: it will succeed if we set the control to create.
        wa, plan = run_checks(
            *run_args,
            expecteds = expecteds_create,
            controls = 'create-parent',
        )

    else:
        # Scenario: case-insensitive system: renaming will succeed
        # because skip-same is the default.
        wa, plan = run_checks(
            *run_args,
            expecteds = expecteds_skip,
            inventory = exp_inv,
        )

        # Scenario: but it will fail if we disable skip-same.
        wa, plan = run_checks(
            *run_args,
            controls = 'halt-same',
            expecteds = expecteds_no_skip,
            failure = True,
            no_change = True,
            reason = PN.same,
            inventory = exp_invH,
        )

@pytest.mark.skip(reason = 'overhaul')
def test_missing_orig(tr, create_wa):
    # Paths and args.
    origs = ('a', 'b')
    news = ('a.new', 'b.new')
    missing_origs = ('c', 'd')
    missing_news = ('c.new', 'd.new')
    inputs = origs + missing_origs + news + missing_news
    run_args = (tr, create_wa, origs, news)
    exp_inv = dict(
        active = ['a', 'b'],
        skipped = ['c', 'd'],
    )
    exp_invH = dict(
        active = exp_inv['active'],
        excluded = exp_inv['skipped'],
    )

    # Scenario: some orig paths are missing.
    # By default, offending paths are skipped.
    wa, plan = run_checks(
        *run_args,
        inputs = inputs,
        rootless = True,
        inventory = exp_inv,
    )

    # Renaming will be rejected if we set the control to halt.
    wa, plan = run_checks(
        *run_args,
        inputs = inputs,
        controls = 'halt-missing',
        rootless = True,
        failure = True,
        no_change = True,
        reason = PN.missing,
        inventory = exp_invH,
    )

    # Or if we use strict mode.
    wa, plan = run_checks(
        *run_args,
        inputs = inputs,
        strict = True,
        rootless = True,
        failure = True,
        no_change = True,
        reason = PN.missing,
        inventory = exp_invH,
    )

@pytest.mark.skip(reason = 'overhaul')
def test_orig_type(tr, create_wa):
    # Paths and args.
    TARGET = 'c.target'
    origs = ('a', 'b', f'c->{TARGET}')
    news = ('a.new', 'b.new', 'c.new')
    extras = (TARGET,)
    expecteds = ('a.new', 'b.new', 'c', TARGET)
    exp_inv = '..s'
    exp_invH = exp_inv.replace('s', 'E')
    run_args = (tr, create_wa, origs, news)

    # Scenario: some orig paths are not regular files.
    # Renaming will be rejected if we set the control to halt.
    wa, plan = run_checks(
        *run_args,
        extras = extras,
        controls = 'halt-type',
        failure = True,
        no_change = True,
        reason = PN.type,
        inventory = exp_invH,
    )

    # Scenario: same. By default, offending paths are skipped.
    wa, plan = run_checks(
        *run_args,
        extras = extras,
        expecteds = expecteds,
        inventory = exp_inv,
    )

def test_new_exists(tr, create_wa):
    # Paths and args.
    origs = ('a', 'b', 'c')
    news = ('a.new', 'b.new', 'c.new')
    extras = ('a.new',)
    expecteds_skip = ('a', 'a.new', 'b.new', 'c.new')
    expecteds_clobber = news
    exp_inv = 's..'
    strict = 'exists'
    reason = Failure(FN.strict, strict)
    run_args = (tr, create_wa, origs, news)

    # Scenario: one of new paths already exists.
    # By default, the plan will forge ahead and clobber.
    wa, plan = run_checks(
        *run_args,
        extras = extras,
        expecteds = expecteds_clobber,
    )

    # User can skip the affected renamings.
    wa, plan = run_checks(
        *run_args,
        extras = extras,
        expecteds = expecteds_skip,
        skip = PN.exists,
        inventory = exp_inv,
    )

    # Or halt the plan in strict mode.
    wa, plan = run_checks(
        *run_args,
        extras = extras,
        strict = strict,
        failure = True,
        no_change = True,
        reason = reason,
    )

@pytest.mark.skip(reason = 'overhaul')
def test_new_exists_diff(tr, create_wa):
    # Paths and args.
    origs = ('a', 'b', 'c')
    news = ('a.new', 'b.new', 'c.new')
    extras = ('a.new/',)
    extras_full = ('a.new/', 'a.new/foo')
    expecteds_skip = ('a',) + news
    exp_inv = 's..'
    exp_invH = exp_inv.replace('s', 'E')
    run_args = (tr, create_wa, origs, news)

    # Scenario 1: one of new paths already exists and it
    # differs in type form the orig path.
    # 1A: By default, offending paths are skipped.
    wa, plan = run_checks(
        *run_args,
        extras = extras,
        expecteds = expecteds_skip,
        inventory = exp_inv,
    )

    # 1B: Renaming will be rejected if we set the control to halt.
    wa, plan = run_checks(
        *run_args,
        extras = extras,
        controls = 'halt-exists-diff',
        failure = True,
        no_change = True,
        reason = PN.exists_diff,
        inventory = exp_invH,
    )

    # 1C: Renaming will also succeed if allow clobber.
    wa, plan = run_checks(
        *run_args,
        extras = extras,
        controls = 'clobber-exists-diff',
    )

    # Scenario 2: same as initial scenario, but the existing
    # directory is also non-empty.
    # 2A: By default, offending paths are skipped.
    wa, plan = run_checks(
        *run_args,
        extras = extras_full,
        expecteds = expecteds_skip + extras_full,
        inventory = exp_inv,
    )

    # 2B: Renaming will be rejected if we set the control to halt.
    wa, plan = run_checks(
        *run_args,
        extras = extras_full,
        controls = 'halt-exists-full',
        failure = True,
        no_change = True,
        reason = PN.exists_full,
        inventory = exp_invH,
    )

    # 2C: And it will succeed if we allow clobber.
    wa, plan = run_checks(
        *run_args,
        extras = extras_full,
        expecteds = news,
        controls = 'clobber-exists-full',
    )

@pytest.mark.skip(reason = 'overhaul')
def test_new_exists_diff_parents(tr, create_wa):
    # Paths and args.
    origs = ('a', 'b')
    news = ('a.new', 'xy/b.new')
    extras = ('xy/', 'xy/b.new')
    expecteds = ('a.new', 'b') + extras
    exp_inv = '.s'
    exp_invH = exp_inv.replace('s', 'E')
    run_args = (tr, create_wa, origs, news)

    # Scenario: one of new paths already exists and
    # it parent directory is different than orig path.
    # Renaming will be rejected if we set the control to halt.
    wa, plan = run_checks(
        *run_args,
        extras = extras,
        controls = 'halt-exists',
        failure = True,
        no_change = True,
        reason = PN.exists,
        inventory = exp_invH,
    )

    # Scenario: same. By default, offending paths are skipped.
    wa, plan = run_checks(
        *run_args,
        extras = extras,
        expecteds = expecteds,
        inventory = exp_inv,
    )

@pytest.mark.skip(reason = 'overhaul')
def test_new_exists_different_case(tr, create_wa):
    # Paths and args.
    origs = ('a', 'b', 'c')
    news = ('a.new', 'b.new', 'c.new')
    extras = ('B.NEW',)
    exp_inv = '.s.'
    exp_invH = exp_inv.replace('s', 'E')
    run_args = (tr, create_wa, origs, news)

    if case_sensitivity() == FS_TYPES.case_sensitive:
        # Scenario: on a case-sensitive system, renaming should
        # succeed because b.new and B.NEW are different files.
        wa, plan = run_checks(
            *run_args,
            extras = extras,
        )
    else:
        # Scenario: but on a non-case-sensitive system,
        # renaming will be rejected if we set the control to halt.
        wa, plan = run_checks(
            *run_args,
            extras = extras,
            controls = 'halt-exists',
            failure = True,
            no_change = True,
            reason = PN.exists,
            inventory = exp_invH,
        )

        # Scenario: renaming will succeed if we request clobbering.
        # Also note that the case of b.new will agree the the
        # users inputs (in news), not the original case of
        # that path (B.NEW).
        wa, plan = run_checks(
            *run_args,
            extras = extras,
            expecteds = news,
            controls = 'clobber-exists',
        )

@pytest.mark.skip(reason = 'overhaul')
def test_new_exists_case_change_renaming(tr, create_wa):
    # Paths and args.
    origs = ('x/a',)
    news = ('x/A',)
    expecteds = ('x',) + news
    run_args = (tr, create_wa, origs, news)

    # Scenario: renaming should succeed regardless of
    # the file system case-sensitivivity because the rename
    # operation involves a case-change renaming.
    wa, plan = run_checks(
        *run_args,
        expecteds = expecteds,
    )

@pytest.mark.skip(reason = 'overhaul')
def test_new_exists_recase(tr, create_wa):
    # Paths and args.
    origs = ('xyz',)
    news = ('xyZ',)
    exp_inv = 's'
    run_args = (tr, create_wa, origs, news)

    # Reason for failure will vary by file system type.
    if case_sensitivity() == FS_TYPES.case_sensitive:
        reason = PN.missing
    else:
        reason = FN.all_filtered

    # Scenario: user reverses order of news and origs when supplying inputs.
    # Renaming will be rejected because all renamings will be skipped, either
    # due to PN.missing (case-sensitive) or PN.recase (case-insensitive).
    wa, plan = run_checks(
        *run_args,
        inputs = news + origs,
        rootless = True,
        failure = True,
        no_change = True,
        reason = FN.all_filtered,
        inventory = False,
    )

    # The precise problem will vary by file system type.
    if case_sensitivity() == FS_TYPES.case_sensitive:
        pn = PN.missing
    else:
        pn = PN.recase
    assert plan.skipped[0].prob_name == pn
    assert len(plan.active) == 0

@pytest.mark.skip(reason = 'overhaul')
def test_new_exists_non_empty(tr, create_wa):
    # Paths and args.
    origs = ('a/', 'b', 'c')
    news = ('a.new', 'b.new', 'c.new')
    extras = ('a.new/', 'a.new/foo')
    exp_inv = 's..'
    exp_invH = exp_inv.replace('s', 'E')
    run_args = (tr, create_wa, origs, news)

    # Scenario: don't include the extras. Renaming succeeds.
    wa, plan = run_checks(*run_args)

    # Scenario: include extras and set the relevant
    # control to halt. Renaming is rejected because
    # the a.new directory already exists and is non-empty.
    wa, plan = run_checks(
        *run_args,
        extras = extras,
        controls = 'halt-exists-full',
        failure = True,
        no_change = True,
        reason = PN.exists_full,
        inventory = exp_invH,
    )

    # Scenario: if we exclude the last extras path, the
    # existing directory will be empty and renaming succeeds.
    wa, plan = run_checks(
        *run_args,
        extras = extras[:-1],
        controls = 'clobber-exists',
    )

@pytest.mark.skip(reason = 'overhaul')
def test_new_parent_missing(tr, create_wa):
    # Paths and args.
    origs = ('a', 'b', 'c')
    news = ('a.new', 'b.new', 'xy/zzz/c.new')
    expecteds_skip = ('a.new', 'b.new', 'c')
    expecteds_create = news + ('xy/', 'xy/zzz/')
    exp_inv = '..s'
    exp_invH = exp_inv.replace('s', 'E')
    run_args = (tr, create_wa, origs, news)

    # Scenario: a new-parent is missing.
    # Renaming will be rejected if we set the control to halt.
    wa, plan = run_checks(
        *run_args,
        controls = 'halt-parent',
        failure = True,
        no_change = True,
        reason = PN.parent,
        inventory = exp_invH,
    )

    # Scenario: same. By default, offending paths are skipped.
    wa, plan = run_checks(
        *run_args,
        expecteds = expecteds_skip,
        inventory = exp_inv,
    )

    # Scenario: renaming will succeed if we create the missing parents.
    wa, plan = run_checks(
        *run_args,
        expecteds = expecteds_create,
        controls = 'create-parent',
    )

@pytest.mark.skip(reason = 'overhaul')
def test_news_collide(tr, create_wa):
    # Paths and args.
    origs = ('a', 'b', 'c')
    news = ('a.new', 'b.new', 'a.new')
    expecteds_skip = ('a', 'b.new', 'c')
    expecteds_clobber = ('a.new', 'b.new')
    run_args = (tr, create_wa, origs, news)
    exp_inv = 's.s'
    exp_invH = exp_inv.replace('s', 'E')

    # Scenario: some new paths collide.
    # By default, offending paths are skipped.
    wa, plan = run_checks(
        *run_args,
        expecteds = expecteds_skip,
        inventory = exp_inv,
    )

    # Renaming will be rejected if we set the control to halt.
    wa, plan = run_checks(
        *run_args,
        controls = 'halt-collides',
        failure = True,
        no_change = True,
        reason = PN.collides,
        inventory = exp_invH,
    )

    # Renaming will succeed if we request clobbering.
    wa, plan = run_checks(
        *run_args,
        expecteds = expecteds_clobber,
        controls = 'clobber-collides',
    )

@pytest.mark.skip(reason = 'overhaul')
def test_news_collide_orig_missing(tr, create_wa):
    # Paths and args.
    origs = ('a', 'b', 'c', 'd')
    news = ('a.new', 'b.new', 'c.new', 'a.new')
    inputs = origs + news
    run_args = (tr, create_wa, origs[:-1], news)
    exp_inv = dict(
        active = ['a', 'b', 'c'],
        excluded = ['d'],
    )

    # Scenario: inputs to RenamingPlan include all origs and news,
    # but we tell the WorkArea to create only the first 3 origs.
    #
    # As a result, the 'd' path has two problem: orig is missing
    # and its new path collides with another new path.
    #
    # But only the first problem will be reported.
    wa, plan = run_checks(
        *run_args,
        inputs = inputs,
        controls = 'halt-missing',
        rootless = True,
        failure = True,
        no_change = True,
        reason = PN.missing,
        inventory = exp_inv,
    )

@pytest.mark.skip(reason = 'overhaul')
def test_news_collide_case(tr, create_wa):
    # Paths and args.
    origs = ('a', 'b', 'c')
    news = ('a.new', 'b.new', 'B.NEW')
    expecteds_skip = ('a.new', 'b', 'c')
    expecteds_clobber = ('a.new', 'B.NEW')
    exp_inv = '.ss'
    exp_invH = exp_inv.replace('s', 'E')
    run_args = (tr, create_wa, origs, news)

    # Scenario: new paths "collide" in a case-insensitive way.
    if case_sensitivity() == FS_TYPES.case_sensitive:
        # If file system is case-sensitive, there is no collision.
        # Renaming will succeed.
        wa, plan = run_checks(*run_args)
    else:
        # On case-insensitive system, renaming will succeed
        # because offending paths will be skipped.
        wa, plan = run_checks(
            *run_args,
            expecteds = expecteds_skip,
            inventory = exp_inv,
        )

        # Renaming will be rejected if we set the control to halt.
        wa, plan = run_checks(
            *run_args,
            controls = 'halt-collides',
            failure = True,
            no_change = True,
            reason = PN.collides,
            inventory = exp_invH,
        )

@pytest.mark.skip(reason = 'overhaul')
def test_news_collide_diff(tr, create_wa):
    # Paths and args.
    SAME = 'a.new'
    origs = ('a/', 'b', 'c', 'd/')
    news = (SAME, 'b.new', SAME, SAME)
    expecteds_skip = ('a', 'b.new', 'c', 'd')
    expecteds_clobber = ('a.new', 'b.new')
    run_args = (tr, create_wa, origs, news)
    exp_inv = 's.ss'
    exp_invH = exp_inv.replace('s', 'E')

    # Scenario: some new paths collide and differ in type.
    # By default, offending paths are skipped.
    wa, plan = run_checks(
        *run_args,
        expecteds = expecteds_skip,
        inventory = exp_inv,
    )

    # Renaming will be rejected if we set the control to halt.
    wa, plan = run_checks(
        *run_args,
        controls = 'halt-collides-diff',
        failure = True,
        no_change = True,
        reason = PN.collides_diff,
        inventory = exp_invH,
    )

    # Renaming will succeed if we request clobbering.
    wa, plan = run_checks(
        *run_args,
        expecteds = expecteds_clobber,
        controls = 'clobber-collides-diff',
    )

@pytest.mark.skip(reason = 'overhaul')
def test_news_collide_full(tr, create_wa):
    # Paths and args.
    SAME = 'a.new'
    origs = ('a/', 'b', 'c/')
    news = (SAME, 'b.new', SAME)
    extras = ('c/foo',)
    expecteds_skip = ('a', 'b.new', 'c') + extras
    expecteds_clobber = ('a.new', 'a.new/foo', 'b.new')
    run_args = (tr, create_wa, origs, news)
    exp_inv = 's.s'

    # Scenario: some new paths collide and differ in type.
    # By default, offending paths are skipped.
    wa, plan = run_checks(
        *run_args,
        extras = extras,
        expecteds = expecteds_skip,
        inventory = exp_inv,
    )

    # If either applicable control is set to halt, the
    # renaming plan will be rejected.
    scenarios = (
        dict(
            controls = 'halt-collides-full',
            reason = PN.collides_full,
            inventory = 'E.s',
        ),
        dict(
            controls = 'halt-collides',
            reason = PN.collides,
            inventory = 's.E',
        ),
        dict(
            controls = 'halt-collides halt-collides-full',
            reason = PN.collides,
            inventory = 'E.E',
        ),
    )
    for kws in scenarios:
        wa, plan = run_checks(
            *run_args,
            extras = extras,
            failure = True,
            no_change = True,
            **kws,
        )

    # If we request clobbering, renaming succeeds.
    wa, plan = run_checks(
        *run_args,
        extras = extras,
        controls = 'clobber-collides-full clobber-collides',
        expecteds = expecteds_clobber,
    )

@pytest.mark.skip(reason = 'overhaul')
def test_failures_skip_all(tr, create_wa):
    # Paths and args.
    origs = ('a', 'b', 'c')
    news = ('Z', 'Z', 'Z')
    exp_inv = 'sss'
    run_args = (tr, create_wa, origs, news)

    # Scenario: all new paths collide. Renaming will be rejected
    # because by default offending paths will be filtered out,
    # leaving nothing to rename.
    wa, plan = run_checks(
        *run_args,
        failure = True,
        no_change = True,
        reason = FN.all_filtered,
        inventory = exp_inv,
    )

####
# Other.
####

@pytest.mark.skip(reason = 'overhaul')
def test_renaming(tr):
    rn = Renaming('a', 'a.new')
    assert rn.prob_name is None
    nm = PN.equal
    rn.problem = Problem(nm)
    assert rn.prob_name == nm

@pytest.mark.skip(reason = 'overhaul')
def test_unexpected_clobber(tr, create_wa):
    # Paths and args.
    VICTIM = 'b.new'
    origs = ('a', 'b', 'c')
    news = ('a.new', VICTIM, 'c.new')
    expecteds = ('a.new', 'b', 'c', VICTIM)
    run_args = (tr, create_wa, origs, news)

    # Helper to create an unexpected clobbering situation
    # in the middle of renaming.
    def set_call_at(wa, plan):
        f = lambda _: Path(VICTIM).touch()
        plan.call_at = (news.index(VICTIM), f)

    # Scenario: basic renaming; it works.
    wa, plan = run_checks(*run_args, rootless = True)

    # Scenario: but if we create the clobbering victim in the middle of
    # renaming, RenamingPlan.rename_paths() will raise an exception and
    # renaming will be aborted in the midway through.
    wa, plan, einfo = run_checks(
        *run_args,
        rootless = True,
        expecteds = expecteds,
        early_checks = set_call_at,
        failure = True,
        check_failure = False,
        return_einfo = True,
    )
    err = einfo.value
    assert err.msg == MF.unrequested_clobber
    assert err.params['orig'] == 'b'
    assert err.params['new'] == VICTIM

