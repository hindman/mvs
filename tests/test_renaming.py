from mvs.renaming import Renaming
from mvs.problems import Problem, PROBLEM_NAMES as PN

def test_renaming(tr):
    rn = Renaming('a', 'a.new')
    assert rn.prob_name is None
    nm = PN.collides
    rn.problem = Problem(nm)
    assert rn.prob_name == nm

