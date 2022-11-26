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

@dataclass
class ExitCondition:
    msg: str

@dataclass
class RenamePair:
    # A data object to hold an original path and the corresponding new path.
    orig: str
    new: str
    failure: Failure = None
    exclude: bool = False
    create_parent: bool = False
    clobber: bool = False

    @property
    def equal(self):
        return self.orig == self.new

    @property
    def failed(self):
        return bool(self.failure)

    @property
    def formatted(self):
        paths = f'{self.orig}\n{self.new}\n'
        if self.failed:
            return f'{self.failure.msg}:\n{paths}'
        else:
            return paths

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

