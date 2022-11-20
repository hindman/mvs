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

def test_preliminary_work(tr):

    # Paths.
    # TODO: figure out how to simplify this type of stuff.
    #
    #   @dataclass(frozen = True)
    #   class FakeFileSys:
    #      origs
    #      news
    #
    #   @property
    #   def inputs():
    #      return self.origs + self.news
    #
    #   @property
    #   def exp_file_sys():
    #      return {p : True for p in self.news}
    #
    file_sys = ('a', 'b', 'c')
    exp_file_sys = ('a1', 'b1', 'c1')
    inputs = file_sys + exp_file_sys
    exp_file_sys = {p : True for p in exp_file_sys}

    # Scenario: no structures.
    plan = RenamingPlan(
        inputs,
        file_sys = file_sys,
    )
    with pytest.raises(BmvError) as einfo:
        plan.rename_paths()
    assert einfo.value.params['msg'] == FAIL.prepare_failed
    assert_failed_because(plan, FAIL.parsing_no_structures)

    # Scenario: now set the structure.
    plan = RenamingPlan(
        inputs,
        structure = STRUCTURES.flat,
        file_sys = file_sys,
    )
    plan.prepare()
    plan.rename_paths()
    assert plan.file_sys == exp_file_sys

