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

