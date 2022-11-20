from dataclasses import dataclass

@dataclass
class RenamePair:
    # A data object to hold an original path and the corresponding new path.
    orig: str
    new: str
    create_parent: bool = False
    clobber: bool = False

    @property
    def formatted(self):
        return f'{self.orig}\n{self.new}\n'

    @property
    def equal(self):
        return self.orig == self.new

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
class RenamePairFailure(Failure):
    rp: RenamePair

    @property
    def formatted(self):
        return f'{self.msg}:\n{self.rp.formatted}'

@dataclass
class RpFilterFailure(RenamePairFailure):
    pass

@dataclass
class RpRenameFailure(RenamePairFailure):
    pass

@dataclass
class RpEqualFailure(RenamePairFailure):
    pass

@dataclass
class RpMissingFailure(RenamePairFailure):
    pass

@dataclass
class RpMissingParentFailure(RenamePairFailure):
    pass

@dataclass
class RpExistsFailure(RenamePairFailure):
    pass

@dataclass
class RpCollsionFailure(RenamePairFailure):
    pass

@dataclass
class ExitCondition:
    msg: str

class Kwexception(Exception):

    def __init__(self, msg = '', **kws):
        d = {'msg': msg}
        d.update(kws)
        super(Kwexception, self).__init__(d)

    def __str__(self):
        return '{}\n'.format(self.params)

    @property
    def params(self):
        return self.args[0]

    @classmethod
    def new(cls, error, **kws):
        # Takes an Exception and keyword arguments. If the error is already a
        # BmvError, update its params. Otherwise, return a new error.
        if isinstance(error, BmvError):
            for k, v in kwargs.items():
                error.params.setdefault(k, v)
            return error
        else:
            return cls(**kwargs)

class BmvError(Kwexception):
    pass

