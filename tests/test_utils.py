import pytest

from bmv.utils import BmvError

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

    # Create BmvError via the classmethod new(), with a ValueError.
    kws = dict(msg = 'frobnosticate', a = 11, b = 22)
    msg0 = 'blort blort'
    e0 = ValueError(msg0)
    exp = {
        'orig_error': 'ValueError',
        'orig_msg': msg0,
        **kws,
    }
    e = BmvError.new(e0, **kws)
    assert e.params == exp

    # Create BmvError via the classmethod new(), with a BmvError.
    kws = dict(msg = 'frobnosticate', a = 11, b = 22)
    extra = dict(a = 9999, x = 3333, y = 2222)
    e0 = BmvError(**kws)
    e = BmvError.new(e0, **extra)
    exp = {**kws, **extra}
    assert e.params == exp

