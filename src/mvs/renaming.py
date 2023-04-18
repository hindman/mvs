from dataclasses import dataclass
from short_con import constants

from .problems import Problem

####
# Renaming type.
#
# Stored in Renaming.name_change_type. Refers only to how the
# proposed renaming would affect the name-portion of the path.
####

NAME_CHANGE_TYPES = constants('NameChangeTypes', (
    'noop',
    'name_change',
    'case_change',
))

####
# A data object to hold information about a single renaming.
####

@dataclass
class Renaming:
    # Paths.
    orig: str
    new: str

    # Path EXISTENCES.
    exist_orig: int = None
    exist_new: int = None
    exist_new_parent: int = None

    # Path types.
    type_orig: str = None
    type_new: str = None

    # The renaming type and whether orig and new have the same parents.
    name_change_type: str = None
    same_parents: bool = None

    # Whether the orig and new paths points to non-empty directories.
    full_orig: bool = False
    full_new: bool = False

    # Attributes for problems.
    # - Problem with the Renaming, if any.
    # - Whether user code filtered out the Renaming.
    # - Whether to create new-parent before renaming.
    # - Whether renaming will clobber something.
    # - Whether renaming will involve case-change-only renaming (ie self-clobber).
    problem: Problem = None
    filtered: bool = False
    create: bool = False
    clobber: bool = False
    clobber_self: bool = False

    @property
    def prob_name(self):
        return getattr(self.problem, 'name', None)

    @property
    def formatted(self):
        p = self.problem
        prefix = f'# Problem: {p.sid}\n' if p else ''
        return f'{prefix}{self.orig}\n{self.new}\n'

