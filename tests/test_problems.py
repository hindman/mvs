import pytest

from mvs.problems import Problem, ProblemControl, PROBLEM_NAMES as PN

def test_problem_names_for(tr):
    # Just exercising the code.
    assert Problem.names_for('create') == ('parent',)

def test_problem_control(tr):
    # Just exercising the code.
    pc1 = ProblemControl('skip-parent')
    pc2 = ProblemControl('skip-parent')
    pc3 = ProblemControl('create-parent')
    exp = set((pc1, pc3))
    got = set((pc1, pc2, pc3))
    assert got == exp
    assert pc1 == pc2

