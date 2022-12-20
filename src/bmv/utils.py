import subprocess
from dataclasses import dataclass

def read_from_file(path):
    with open(path) as fh:
        return fh.read()

def read_from_clipboard():
    cp = subprocess.run(
        ['pbpaste'],
        capture_output = True,
        check = True,
        text = True,
    )
    return cp.stdout

def write_to_clipboard(text):
    subprocess.run(
        ['pbcopy'],
        check = True,
        text = True,
        input = text,
    )

@dataclass(frozen = True)
class RenamePair:
    # A data object to hold an original path and the corresponding new path.
    orig: str
    new: str
    exclude: bool = False
    create_parent: bool = False
    clobber: bool = False

    @property
    def equal(self):
        return self.orig == self.new

    @property
    def formatted(self):
        return f'{self.orig}\n{self.new}\n'

class Kwexception(Exception):

    '''

    Constructor should take *xs, which is consistent with other Exception classes.

    Whether to set kws['msg']:
        yes  # The default, conditional on (a) 1 element in xs, (b) 'msg' not in kws.
        no

    What to pass into super() call: control it via class configuration:
        kws   # The dict.
        xs    # Like Python.
        msg   # Like Python but user can explicitly pass msg as a keyword arg.

    How to stringify: configure with the same settings.

    Some code:

        SET_MSG = True
        SUPER_ARG = 'kws'
        STRINGIFY = 'kws'

        def __init__(self, *xs, **kws):
            if self.SET_MSG and len(xs) == 1 and 'msg' not in kws:
                d = {'msg': xs[0]}
                d.update(kws)

            if self.SUPER_ARG == 'kws':
                xs = kws
            elif self.SUPER_ARG == 'msg':
                xs = kws['msg']

            super(Kwexception, self).__init__(*xs)

        def is_msg(self, xs):
            return len(xs) == 1 and isinstance(xs[0], str)

        def __str__(self):
            if self.is_msg(self.args):
            return str(self.params)

        @property
        def params(self):
            return self.args[0]

        @property
        def msg(self):
            return self.params['msg']

    '''

    def __init__(self, msg = '', **kws):
        d = {'msg': msg}
        d.update(kws)
        super(Kwexception, self).__init__(d)

    @classmethod
    def new(cls, e, **kws):
        if isinstance(e, Kwexception):
            e.params.update(kws)
            return e
        else:
            return cls(
                orig_error = type(e).__name__,
                orig_msg = str(e),
                **kws,
            )

    def __str__(self):
        return str(self.params)

    @property
    def params(self):
        return self.args[0]

    @property
    def msg(self):
        return self.params['msg']

class BmvError(Kwexception):
    pass

