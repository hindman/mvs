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

    Avoid designing the class so that data in xs can be lost.

    The purposes of Kwexception.new():

        - Convert another error type to the error-type known by your project.
          [see NEW_CONVERT]

        - Augment a Kwexception instance with more keyword args, either in the
          fashion of dict.update or dict.setdefault. [see NEW_UPDATE]

        - Add some attributes from the initial Exception to the params. [see
          NEW_INITIAL]

        - But its purposes do not include, replacing or improving upon Python's
          traceback generation or handling of __context__ and __cause__. Let
          the user raise-with as needed.

    Is STRINGIFY really needed? Defer for now.

        There might be one valid use case: someone who wants stringification to
        be just the self.msg (or less compellingly, self.params), but they need
        the underlying self.args to be a tuple with multiple elements (maybe a
        named tuple).

        But this could be added later without changing anything else.

    Some code:

        MOVE = 'move'
        COPY = 'copy'
        MSG = 'msg'

        SET_MSG = MOVE            # MOVE|COPY|None
        SUPER_PARAMS = True       # .
        NEW_CONVERT = True        # .
        NEW_UPDATE = True         # If False, will use setdefault instead.
        NEW_INITIAL = True        # .

        def __init__(self, *xs, **kws):

            # Put the msg into kws, as the first key.
            if xs and self.SET_MSG in (self.MOVE, self.COPY) and self.MSG not in kws:
                d = {self.MSG: xs[0]}
                d.update(kws)
                kws = d
                if self.SET_MSG == self.MOVE:
                    xs = xs[1:]

            # Add kws to xs so that it will be included in the super() call.
            if self.SUPER_PARAMS:
                xs = xs + (kws,)

            # Set params and make the super() call.
            self.params = kws
            super().__init__(*xs)

        @property
        def msg(self):
            return self.params.get(self.MSG, None)

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
                # TODO: switch to these keywords:
                # initial_error = type(e).__name__,
                # initial_args = e.args,
                # initial_str = str(e),

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

