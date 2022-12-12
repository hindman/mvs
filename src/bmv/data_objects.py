from dataclasses import dataclass

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

    def __init__(self, msg = '', **kws):
        d = {'msg': msg}
        d.update(kws)
        super(Kwexception, self).__init__(d)

    def __str__(self):
        return str(self.params)

    @property
    def params(self):
        return self.args[0]

class BmvError(Kwexception):
    pass

