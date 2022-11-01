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
class RpFilterFailure(RPFailure):
    pass

@dataclass
class RpRenameFailure(RPFailure):
    pass

@dataclass
class RpEqualFailure(RPFailure):
    pass

@dataclass
class RpMissingFailure(RPFailure):
    pass

@dataclass
class RpMissingParentFailure(RPFailure):
    pass

@dataclass
class RpExistsFailure(RPFailure):
    pass

@dataclass
class RpCollsionFailure(RPFailure):
    pass

@dataclass
class ExitCondition:
    msg: str

