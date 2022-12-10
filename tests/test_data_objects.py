import pytest

from bmv.data_objects import BmvError

def test_bmv_error(tr):

    # Helper to check BmvError instances.
    def check(e, exp):
        assert isinstance(e, BmvError)
        assert e.params == exp
        assert str(e) == str(exp)

    # Some keyword arguments.
    initial = {'msg': 'hello', 'a': 1, 'b': 2}
    popped = dict(initial)
    msg = popped.pop('msg')

    # Basic usage: create a BmvError via keyword parameters.
    e1 = BmvError(**initial)
    check(e1, initial)

    # Same scenario, but msg is given positionally.
    e2 = BmvError(msg, **popped)
    check(e2, initial)

