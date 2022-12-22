import subprocess
from dataclasses import dataclass

from kwexception import Kwexception

class BmvError(Kwexception):
    pass

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

