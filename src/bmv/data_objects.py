from dataclasses import dataclass

@dataclass
class Failure:
    msg: str

@dataclass
class OptsFailure(Failure):
    pass

@dataclass
class ParseFailure(Failure):
    pass

@dataclass
class UserCodeExecFailure(Failure):
    pass

@dataclass
class NoPathsFailure(Failure):
    pass

@dataclass
class RpFilterFailure(Failure):
    pass

@dataclass
class RpRenameFailure(Failure):
    pass

@dataclass
class RpEqualFailure(Failure):
    pass

@dataclass
class RpMissingFailure(Failure):
    pass

@dataclass
class RpMissingParentFailure(Failure):
    pass

@dataclass
class RpExistsFailure(Failure):
    pass

@dataclass
class RpCollsionFailure(Failure):
    pass

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

@dataclass
class RpFailure(Failure):
    rp: RenamePair
    failure: str

    @property
    def formatted(self):
        if self.rp:
            return f'{self.msg}:\n{self.rp.formatted}'
        else:
            return self.msg

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

