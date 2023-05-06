from mvs.renaming import Renaming
from mvs.problems import Problem, PROBLEM_NAMES as PN

def test_renaming_properties(tr):
    # Create a Renaming.
    rn = Renaming('a', 'AA')
    nm = PN.collides
    exp = 'a\nAA\n'

    # Check formatted property.
    assert rn.formatted == exp

    # Exercise prob_name property before and after adding a Problem.
    assert rn.prob_name is None
    rn.problem = Problem(nm)
    assert rn.prob_name == nm

    # Check formatted property now that there is a Problem.
    assert rn.formatted == f'# Problem: {nm}\n{exp}'

