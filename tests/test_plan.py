import pytest
from itertools import chain
from pathlib import Path

from mvs.constants import CON, STRUCTURES
from mvs.filesys import FS_TYPES, case_sensitivity
from mvs.messages import MSG_FORMATS as MF
from mvs.plan import RenamingPlan
from mvs.renaming import Renaming
from mvs.utils import MvsError

from mvs.problems import (
    FAILURE_NAMES as FN,
    FAILURE_VARIETIES as FV,
    Failure,
    PROBLEM_NAMES as PN,
    PROBLEM_VARIETIES as PV,
    Problem,
    StrictMode,
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
        n_preps = int(
            prepare_before or
            prepare_only or
            diagnostics
        )
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
            # If dict, it maps ATTR => [ORIGS].
            exp = {
                attr : sorted(inventory.get(attr, []))
                for attr in INV_MAP.values()
            }
        else:
            # A str or None uses a convenience format based on INV_MAP.
            n = len(wa.origs)
            if inventory is None:
                # Everything in the active bucket.
                inventory = '.'
            if len(inventory) == 1:
                # Single char: all origs end up in same bucket.
                inventory = inventory * n
            assert len(inventory) == n
            pairs = tuple(zip(inventory, wa.origs))
            exp = {
                attr : sorted(o for abbrev, o in pairs if abbrev == k)
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
# When inventory=EMPTY, the assembled inventory will be empty.
EMPTY = '_'
INV_MAP = {
    '.': 'active',
    'f': 'filtered',
    's': 'skipped',
    'X': 'excluded',
}

PLACEHOLDER = 'PLACEHOLDER'

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

def test_structure_origs(tr, create_wa):
    # Paths and args.
    origs = ('a', 'b', 'c')
    news = ('a.new', 'b.new', 'c.new')
    expecteds = ('a.001', 'b.002', 'c.003')
    run_args = (tr, create_wa, origs, news)

    # Scenario: original paths only, plus --rename.
    wa, plan = run_checks(
        *run_args,
        rename_code = 'return o + ".new"',
        structure = STRUCTURES.origs,
        include_news = False,
    )

    # Scenario: original and new paths, plus --rename.
    wa, plan = run_checks(
        *run_args,
        rename_code = 'return n.replace("new", str(seq).zfill(3))',
        expecteds = expecteds,
    )

    # Scenario: original paths only, without --rename.
    wa, plan = run_checks(
        *run_args,
        structure = STRUCTURES.origs,
        include_news = False,
        failure = True,
        reason = Failure(FN.parsing, variety = FV.origs_rename),
        no_change = True,
        inventory = EMPTY,
    )

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
            reason = Failure(FN.parsing, variety = FV.paragraphs),
            no_change = True,
            inventory = EMPTY,
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
        reason = Failure(FN.parsing, variety = FV.imbalance),
        inventory = EMPTY,
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
            reason = Failure(FN.parsing, PLACEHOLDER, variety = FV.row),
            inventory = EMPTY,
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
    code_lambda = lambda o, **kws: o + o
    def code_func(o, **kws): return o + o

    # Scenarios: generate new-paths via user-supplied code.
    for code in (code_str, code_lambda, code_func):
        wa, plan = run_checks(
            *run_args,
            inputs = origs,
            rename_code = code,
            structure = STRUCTURES.origs,
            rootless = True,
        )

    # Make sure we can access all variables passed to user code.
    wa, plan = run_checks(
        *run_args,
        inputs = origs + news,
        rename_code = 'xs = (o, n, po, pn, seq, r, plan)\n    if all(xs): return n',
        rootless = True,
    )

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
        filter_code = 'return not ("d" in o or po.is_dir())',
        structure = STRUCTURES.origs,
        rootless = True,
        inventory = exp_inv,
    )

def test_code_compilation_fails(tr, create_wa):
    # Paths and args.
    origs = ('a', 'b', 'c')
    news = ('aa', 'bb', 'cc')
    run_args = (tr, create_wa, origs, news)
    reason_rename = Failure(FN.code, CON.code_actions.rename, PLACEHOLDER)
    reason_filter = Failure(FN.code, CON.code_actions.filter, PLACEHOLDER)

    # Some bad code to use for renaming and filtering.
    BAD_CODE = 'FUBB BLORT'

    # Helper to check some details about the first uncontrolled Problem.
    def check_fail(plan):
        f = plan.failure
        assert BAD_CODE in f.msg
        assert 'invalid syntax' in f.msg

    # Scenario: invalid renaming code.
    wa, plan = run_checks(
        *run_args,
        structure = STRUCTURES.origs,
        include_news = False,
        rename_code = BAD_CODE,
        failure = True,
        no_change = True,
        reason = reason_rename,
    )

    # Scenario: invalid filtering code.
    wa, plan = run_checks(
        *run_args,
        filter_code = BAD_CODE,
        failure = True,
        no_change = True,
        reason = reason_filter,
    )
    check_fail(plan)

def test_code_execution_fails(tr, create_wa):
    # Paths and args.
    FAILING_ORIG = 'b'
    origs = ('a', FAILING_ORIG, 'c')
    news = ('aa', 'bb', 'cc')
    expecteds_skip = ('aa', FAILING_ORIG, 'cc')
    exp_inv = '.X.'
    strict = StrictMode.EXCLUDED
    reason = Failure(FN.strict, strict)
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
        dict(
            rename_code = rename_code1,
            structure = STRUCTURES.origs,
            include_news = False,
        ),
        dict(
            rename_code = rename_code2,
            structure = STRUCTURES.origs,
            include_news = False,
         ),
        dict(filter_code = filter_code),
    )

    # By default, the offending renamings are excluded.
    for kws in scenarios:
        wa, plan = run_checks(
            *run_args,
            rootless = True,
            expecteds = expecteds_skip,
            inventory = exp_inv,
            **kws,
        )

    # And in strict mode, the renaming will be rejected.
    for kws in scenarios:
        wa, plan = run_checks(
            *run_args,
            rootless = True,
            failure = True,
            no_change = True,
            inventory = exp_inv,
            strict = strict,
            reason = reason,
            **kws,
        )

def test_seq(tr, create_wa):
    # Paths and args.
    origs = ('a', 'b', 'c')
    news = ('a.20', 'b.30', 'c.40')
    run_args = (tr, create_wa, origs, news)

    # Scenario: user defines a sequence and uses
    # its values in user-supplied code.
    wa, plan = run_checks(
        *run_args,
        structure = STRUCTURES.origs,
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
        structure = STRUCTURES.origs,
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
    filter_code = lambda o, **kws: 'd' not in o

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
            'skip',
            'strict',
            'filtered',
            'skipped',
            'excluded',
            'active',
            'failure',
            'prefix_len',
            'tracking_index',
        ))

    # Define a RenamingPlan. Check its as_dict keys
    # both before and after renaming.
    wa, plan = run_checks(
        *run_args,
        rootless = True,
        include_news = False,
        structure = STRUCTURES.origs,
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

def test_prepare_rename_multiple_times(tr, create_wa):
    # Paths and args.
    origs = ('a', 'b', 'c')
    news = ('aa', 'bb', 'cc')
    run_args = (tr, create_wa, origs, news)

    # Scenario: can call plan.prepare() multiple times
    # without causing any trouble: renaming succeeds.
    wa, plan = run_checks(
        *run_args,
        structure = STRUCTURES.origs,
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

def test_equal(tr, create_wa):
    # Paths and args.
    SAME = 'd'
    origs = ('a', 'b', 'c') + (SAME,)
    news = ('a.new', 'b.new', 'c.new') + (SAME,)
    exp_inv = '...X'
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

def test_duplicate(tr, create_wa):
    # Paths and args.
    SAME = 'b'
    origs = ('a', SAME, SAME, SAME)
    news = ('a.new', 'b.new', 'c.new', 'd.new')
    expecteds = ('a.new', SAME)
    exp_inv = '.XXX'
    strict = 'excluded'
    reason = Failure(FN.strict, strict)
    run_args = (tr, create_wa, origs, news)

    # Scenario: the orig paths are not unique.
    # By default, the offending Renaming will be excluded.
    wa, plan = run_checks(
        *run_args,
        expecteds = expecteds,
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

def test_same(tr, create_wa):
    # Paths and args.
    origs = ('foo/xyz', 'BAR/xyz', 'a')
    news = ('FOO/xyz', 'bar/xyz', 'a.new')
    parents_orig = ('foo', 'BAR')
    parents_new = ('FOO', 'bar')
    expecteds_exclude = ('foo/xyz', 'BAR/xyz', 'a.new') + parents_orig
    expecteds_create = news + parents_orig + parents_new
    expecteds_fail = origs + parents_orig
    exp_invX = 'XX.'
    exp_invS = 'ss.'
    run_args = (tr, create_wa, origs, news)

    # Scenarios: for the first two Renaming instances,
    # orig and new differ only in the casing of their parent.
    if case_sensitivity() == FS_TYPES.case_sensitive:
        # Scenario: case-sensitive system: by default, the
        # parents needed for the renaming will be created.
        wa, plan = run_checks(
            *run_args,
            expecteds = expecteds_create,
        )

        # Or the user can skip renamings missing a parent.
        wa, plan = run_checks(
            *run_args,
            skip = PN.parent,
            expecteds = expecteds_exclude,
            inventory = exp_invS,
        )

        # And in strict mode, the plan will fail.
        wa, plan = run_checks(
            *run_args,
            strict = PN.parent,
            failure = True,
            no_change = True,
            expecteds = expecteds_fail,
            reason = Failure(FN.strict, PN.parent),
        )

    else:
        # Scenario: case-insensitive system: by default, the
        # offending renamings will be excluded.
        wa, plan = run_checks(
            *run_args,
            expecteds = expecteds_exclude,
            inventory = exp_invX,
        )

def test_missing_orig(tr, create_wa):
    # Paths and args.
    origs = ('a', 'b')
    news = ('a.new', 'b.new')
    missing_origs = ('c', 'd')
    missing_news = ('c.new', 'd.new')
    INPUTS = origs + missing_origs + news + missing_news
    run_args = (tr, create_wa, origs, news)
    exp_inv = dict(
        active = origs,
        excluded = missing_origs,
    )

    # Scenario: some orig paths are missing.
    # By default, offending paths are excluded.
    wa, plan = run_checks(
        *run_args,
        inputs = INPUTS,
        rootless = True,
        inventory = exp_inv,
    )

    # Renaming will fail in strict mode.
    wa, plan = run_checks(
        *run_args,
        inputs = INPUTS,
        strict = StrictMode.EXCLUDED,
        rootless = True,
        failure = True,
        no_change = True,
        reason = Failure(FN.strict, PN.missing),
        inventory = exp_inv,
    )

def test_orig_type(tr, create_wa):
    # Paths and args.
    TARGET = 'c.target'
    origs = ('a', 'b', f'c->{TARGET}')
    news = ('a.new', 'b.new', 'c.new')
    extras = (TARGET,)
    expecteds = ('a.new', 'b.new', 'c', TARGET)
    exp_inv = '..X'
    run_args = (tr, create_wa, origs, news)

    # Scenario: some orig paths are not regular files.
    # By default, offending paths are excluded.
    wa, plan = run_checks(
        *run_args,
        extras = extras,
        expecteds = expecteds,
        inventory = exp_inv,
    )

    # Renaming will fail in strict mode.
    wa, plan = run_checks(
        *run_args,
        extras = extras,
        strict = StrictMode.EXCLUDED,
        failure = True,
        no_change = True,
        reason = Failure(FN.strict, PN.type),
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
        strict = PN.exists,
        failure = True,
        no_change = True,
        reason = Failure(FN.strict, PN.exists),
    )

def test_new_exists_diff(tr, create_wa):
    # Paths and args.
    origs = ('a', 'b', 'c')
    news = ('a.new', 'b.new', 'c.new')
    extras = ('a.new/',)
    extras_full = extras + ('a.new/foo',)
    expecteds_skip = ('a',) + news
    exp_inv = 's..'
    run_args = (tr, create_wa, origs, news)

    # Scenario 1: one of new paths already exists and it
    # differs in type form the orig path.
    # 1A: By default, renaming will proceed and clobber.
    wa, plan = run_checks(
        *run_args,
        extras = extras,
    )

    # 1B: User can skip offending renamings.
    wa, plan = run_checks(
        *run_args,
        extras = extras,
        skip = PN.exists,
        expecteds = expecteds_skip,
        inventory = exp_inv,
    )

    # 1C: User can halt renaming in strict mode.
    wa, plan = run_checks(
        *run_args,
        extras = extras,
        strict = PN.exists,
        failure = True,
        no_change = True,
        reason = Failure(FN.strict, PN.exists),
    )

    # Scenario 2: same as initial scenario, but the existing
    # directory is also non-empty.
    # 2A: By default, renaming will proceed and clobber.
    wa, plan = run_checks(
        *run_args,
        extras = extras_full,
        expecteds = news,
    )

    # 2B: User can skip offending renamings.
    wa, plan = run_checks(
        *run_args,
        extras = extras_full,
        skip = PN.exists,
        expecteds = expecteds_skip + extras_full,
        inventory = exp_inv,
    )

    # 2C: User can halt renaming in strict mode.
    wa, plan = run_checks(
        *run_args,
        extras = extras_full,
        strict = PN.exists,
        failure = True,
        no_change = True,
        reason = Failure(FN.strict, PN.exists),
    )

def test_new_exists_other(tr, create_wa):
    # Paths and args.
    origs = ('a', 'b', 'c')
    news = ('a.new', 'b.new', 'c.new')
    TARGET = 'c.target'
    extras = (f'c.new->{TARGET}',)
    expecteds = news + ('c',)
    exp_inv = '..X'
    run_args = (tr, create_wa, origs, news)

    # Scenario: one of new paths already exists and it is
    # not a supported path type. By default, the renaming will
    # proceed, excluding the offending renaming.
    wa, plan = run_checks(
        *run_args,
        extras = extras,
        expecteds = expecteds,
        inventory = exp_inv,
    )

    # User can halt renaming in strict mode.
    wa, plan = run_checks(
        *run_args,
        extras = extras,
        strict = StrictMode.EXCLUDED,
        failure = True,
        no_change = True,
        reason = Failure(FN.strict, StrictMode.EXCLUDED),
        inventory = exp_inv,
    )

def test_new_exists_diff_parents(tr, create_wa):
    # Paths and args.
    origs = ('a', 'b')
    news = ('a.new', 'xy/b.new')
    extras = ('xy/', 'xy/b.new')
    expecteds = ('a.new',) + extras
    expecteds_skip = ('a.new', 'b') + extras
    exp_inv = '.s'
    run_args = (tr, create_wa, origs, news)

    # Scenario: one of new paths already exists and
    # its parent directory is different than parent of orig.
    # By default, renaming proceeds and clobbers.
    wa, plan = run_checks(
        *run_args,
        extras = extras,
        expecteds = expecteds,
    )

    # User can skip offending renamings.
    wa, plan = run_checks(
        *run_args,
        extras = extras,
        skip = PN.exists,
        expecteds = expecteds_skip,
        inventory = exp_inv,
    )

    # In strict mode, renaming will fail.
    wa, plan = run_checks(
        *run_args,
        extras = extras,
        strict = PN.exists,
        failure = True,
        no_change = True,
        reason = Failure(FN.strict, PN.exists),
    )

def test_new_exists_different_case(tr, create_wa):
    # Paths and args.
    origs = ('a', 'b', 'c')
    news = ('a.new', 'b.new', 'c.new')
    extras = ('B.NEW',)
    run_args = (tr, create_wa, origs, news)

    # Scenario: one of the new paths exists in a case-altered form.
    if case_sensitivity() == FS_TYPES.case_sensitive:
        # On a case-sensitive system, renaming succeeds,
        # because b.new and B.NEW are different files.
        wa, plan = run_checks(
            *run_args,
            extras = extras,
        )
    else:
        # By default, renaming will proceed via clobbering.
        # Moreover, the new path's casing will agree with the
        # new path, not the original.
        wa, plan = run_checks(
            *run_args,
            extras = extras,
            expecteds = news,
        )

        # And in strict mode, renaming will fail.
        wa, plan = run_checks(
            *run_args,
            extras = extras,
            strict = PN.exists,
            failure = True,
            no_change = True,
            reason = Failure(FN.strict, PN.exists),
        )

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

def test_new_exists_recase(tr, create_wa):
    # Paths and args.
    origs = ('xyz',)
    news = ('xyZ',)
    exp_inv = dict(excluded = news)
    run_args = (tr, create_wa, origs, news)

    # Scenario: user reverses order of news and origs when supplying inputs.
    # Renaming will be rejected because all renamings will be excluded.
    wa, plan = run_checks(
        *run_args,
        inputs = news + origs,
        rootless = True,
        failure = True,
        no_change = True,
        reason = Failure(FN.all_filtered),
        inventory = exp_inv,
    )

    # The precise problem will vary by file system type.
    prob = plan.excluded[0].problem
    if case_sensitivity() == FS_TYPES.case_sensitive:
        assert prob == Problem(PN.missing)
    else:
        assert prob == Problem(PN.noop, variety = PV.recase)

def test_new_exists_non_empty(tr, create_wa):
    # Paths and args.
    origs = ('a/', 'b', 'c')
    news = ('a.new', 'b.new', 'c.new')
    extras = ('a.new/', 'a.new/foo')
    run_args = (tr, create_wa, origs, news)

    # Scenario: a new path exists and it is a non-empty directory.
    # By default, renaming will proceed and clobber.
    wa, plan = run_checks(
        *run_args,
        extras = extras,
        expecteds = news,
    )

    # Scenario: include extras and set the relevant
    # control to halt. Renaming is rejected because
    # the a.new directory already exists and is non-empty.
    wa, plan = run_checks(
        *run_args,
        extras = extras,
        strict = PN.exists,
        failure = True,
        no_change = True,
        reason = Failure(FN.strict, PN.exists),
    )

def test_new_parent_missing(tr, create_wa):
    # Paths and args.
    origs = ('a', 'b', 'c')
    news = ('a.new', 'b.new', 'xy/zzz/c.new')
    expecteds_skip = ('a.new', 'b.new', 'c')
    expecteds_create = news + ('xy/', 'xy/zzz/')
    exp_inv = '..s'
    run_args = (tr, create_wa, origs, news)

    # Scenario: a new-parent is missing.
    # By default, renaming will proceed by creating the parent.
    wa, plan = run_checks(
        *run_args,
        expecteds = expecteds_create,
    )

    # User can skip the renamings with missing parents.
    wa, plan = run_checks(
        *run_args,
        expecteds = expecteds_skip,
        skip = PN.parent,
        inventory = exp_inv,
    )

    # User can halt the renaming in strict mode.
    wa, plan = run_checks(
        *run_args,
        strict = PN.parent,
        failure = True,
        no_change = True,
        reason = Failure(FN.strict, PN.parent),
    )

def test_news_collide(tr, create_wa):
    # Paths and args.
    origs = ('a', 'b', 'c')
    news = ('a.new', 'b.new', 'a.new')
    expecteds_skip = ('a', 'b.new', 'c')
    expecteds_clobber = ('a.new', 'b.new')
    exp_inv = 's.s'
    run_args = (tr, create_wa, origs, news)

    # Scenario: some new paths collide.
    # By default, renaming will proceed and clobber.
    wa, plan = run_checks(
        *run_args,
        expecteds = expecteds_clobber,
    )

    # User can skip the colliding renamings.
    wa, plan = run_checks(
        *run_args,
        expecteds = expecteds_skip,
        inventory = exp_inv,
        skip = PN.collides,
    )

    # User can halt the renaming in strict mode.
    wa, plan = run_checks(
        *run_args,
        strict = PN.collides,
        failure = True,
        no_change = True,
        reason = Failure(FN.strict, PN.collides),
    )

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
        rootless = True,
        expecteds = news[:-1],
        inventory = exp_inv,
    )
    assert plan.excluded[0].problem.name == PN.missing

    # In strict mode, the renaming can be halted.
    wa, plan = run_checks(
        *run_args,
        inputs = inputs,
        rootless = True,
        strict = StrictMode.EXCLUDED,
        failure = True,
        no_change = True,
        reason = Failure(FN.strict, PN.missing),
        inventory = exp_inv,
    )

def test_news_collide_case(tr, create_wa):
    # Paths and args.
    origs = ('a', 'b', 'c')
    news = ('a.new', 'b.new', 'B.NEW')
    expecteds_skip = ('a.new', 'b', 'c')
    expecteds_clobber = ('a.new', 'B.NEW')
    exp_inv = '.ss'
    run_args = (tr, create_wa, origs, news)

    # Scenario: new paths "collide" in a case-insensitive way.
    if case_sensitivity() == FS_TYPES.case_sensitive:
        # If file system is case-sensitive, there is no collision.
        # Renaming will succeed.
        wa, plan = run_checks(*run_args)
    else:
        # On case-insensitive system, renaming will proceed and clobber.
        wa, plan = run_checks(
            *run_args,
            expecteds = expecteds_clobber,
        )

        # User can skip the colliding renamings.
        wa, plan = run_checks(
            *run_args,
            expecteds = expecteds_skip,
            skip = PN.collides,
            inventory = exp_inv,
        )

        # User can halt renaming in strict mode.
        wa, plan = run_checks(
            *run_args,
            strict = PN.collides,
            failure = True,
            no_change = True,
            reason = Failure(FN.strict, PN.collides),
        )

def test_news_collide_diff(tr, create_wa):
    # Paths and args.
    SAME = 'a.new'
    origs = ('a/', 'b', 'c', 'd/')
    news = (SAME, 'b.new', SAME, SAME)
    expecteds_skip = ('a', 'b.new', 'c', 'd')
    expecteds_clobber = ('a.new', 'b.new')
    exp_inv = 's.ss'
    run_args = (tr, create_wa, origs, news)

    # Scenario: some new paths collide and differ in type.
    # By default, renaming will proceed and clobber.
    wa, plan = run_checks(
        *run_args,
        expecteds = expecteds_clobber,
    )

    # User can skipp colliding renamings.
    wa, plan = run_checks(
        *run_args,
        skip = PN.collides,
        expecteds = expecteds_skip,
        inventory = exp_inv,
    )

    # User can halt renaming in strict mode.
    wa, plan = run_checks(
        *run_args,
        strict = PN.collides,
        failure = True,
        no_change = True,
        reason = Failure(FN.strict, PN.collides),
    )

def test_news_collide_full(tr, create_wa):
    # Paths and args.
    SAME = 'a.new'
    origs = ('a/', 'b', 'c/')
    news = (SAME, 'b.new', SAME)
    extras = ('c/foo',)
    expecteds_clobber = ('a.new', 'a.new/foo', 'b.new')
    expecteds_skip = ('a', 'b.new', 'c') + extras
    expecteds_skip_full = ('a', 'b.new', 'a.new', 'a.new/foo')
    exp_inv = 's.s'
    exp_invSF = 's..'
    run_args = (tr, create_wa, origs, news)

    # Scenario: some new paths collide and differ in type,
    # and the directory is non-empty.
    # By default, renaming proceeds and clobbers.
    wa, plan = run_checks(
        *run_args,
        extras = extras,
        expecteds = expecteds_clobber,
    )
    assert plan.active[0].problem == Problem(PN.collides, variety = PV.full)

    # User can skip the colliding renamings.
    wa, plan = run_checks(
        *run_args,
        extras = extras,
        skip = PN.collides,
        expecteds = expecteds_skip,
        inventory = exp_inv,
    )

    # User can skip only the collides-full renaming.
    wa, plan = run_checks(
        *run_args,
        extras = extras,
        skip = 'collides-full',
        expecteds = expecteds_skip_full,
        inventory = exp_invSF,
    )

def test_failures_filter_all(tr, create_wa):
    # Paths and args.
    SAME = 'Z'
    origs = ('a', 'b', 'c')
    news = (SAME, SAME, SAME)
    run_args = (tr, create_wa, origs, news)

    # Scenario: all new paths collide.
    # By default, renaming will proceed and clobber.
    wa, plan = run_checks(
        *run_args,
        expecteds = (SAME,),
    )

    # User can skip colliding renamings.
    # That will filter everything out.
    wa, plan = run_checks(
        *run_args,
        skip = PN.collides,
        failure = True,
        no_change = True,
        reason = Failure(FN.all_filtered),
        inventory = 's',
    )

    # User can halt the renaming in strict mode.
    # That will filter everything out.
    wa, plan = run_checks(
        *run_args,
        strict = PN.collides,
        failure = True,
        no_change = True,
        reason = Failure(FN.strict, PN.collides),
    )

####
# Other.
####

def test_unexpected_clobber(tr, create_wa):
    # Paths and args.
    VICTIM = 'b.new'
    TARGET = 'TARGET'
    origs = ('a', 'b', 'c')
    news = ('a.new', VICTIM, 'c.new')
    expecteds = ('a.new', 'b', 'c', VICTIM)
    run_args = (tr, create_wa, origs, news)

    # Helper to create unexpected clobbering situations
    # in the middle of renaming.
    def toucher(plan):
        Path(VICTIM).touch()

    def linker(plan):
        Path(VICTIM).unlink()
        Path(TARGET).touch()
        Path(VICTIM).symlink_to(TARGET)

    def create_call_at_setter(operation):
        def f(wa, plan):
            plan.call_at = (news.index(VICTIM), operation)
        return f

    # Helper to check stuff across different scenarios.
    def do_checks(err, exp):
        assert err.msg == exp
        assert err.params['orig'] == 'b'
        assert err.params['new'] == VICTIM

    # Scenario 1: basic renaming; it works.
    wa, plan = run_checks(*run_args, rootless = True)

    # Scenario 2: if we create the clobbering victim in the middle of
    # renaming, RenamingPlan.rename_paths() will raise an exception and
    # renaming will be aborted in midway through.
    wa, plan, einfo = run_checks(
        *run_args,
        rootless = True,
        expecteds = expecteds,
        early_checks = create_call_at_setter(toucher),
        failure = True,
        check_failure = False,
        return_einfo = True,
    )
    do_checks(einfo.value, MF.unrequested_clobber)

    # Scenario 3: this time the clobbering victim is expected (because
    # we include it in extras), but during the middle of renaming
    # the new path gets replaced by an unsupported path type.
    # Here the renaming should halt in the middle with a different
    # error message.
    wa, plan, einfo = run_checks(
        *run_args,
        rootless = True,
        extras = (VICTIM,),
        expecteds = expecteds + (TARGET,),
        early_checks = create_call_at_setter(linker),
        failure = True,
        check_failure = False,
        return_einfo = True,
    )
    do_checks(einfo.value, MF.unsupported_clobber)

def test_invalid_skip(tr):
    # Exercise code path involving invalid input for skip.
    inputs = ('a', 'b', 'a.new', 'b.new')
    bad = 'exists-fubb'
    with pytest.raises(MvsError) as einfo:
        plan = RenamingPlan(inputs, skip = bad)
    exp = MF.invalid_skip.format(bad)
    assert einfo.value.msg == exp

