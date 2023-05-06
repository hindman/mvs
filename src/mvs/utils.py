import pyperclip
import sys

from inspect import getsource
from kwexception import Kwexception
from pathlib import Path
from subprocess import run
from tempfile import gettempdir
from time import time

from .constants import CON
from .messages import MSG_FORMATS as MF

####
# An exception class for the project.
####

class MvsError(Kwexception):
    pass

####
# Read/write: clipboard and files.
####

def read_from_clipboard():
    return pyperclip.paste()

def write_to_clipboard(text):
    pyperclip.copy(text)

def read_from_file(path):
    with open(path) as fh:
        return fh.read()

def edit_text(editor, text):
    # Get a temp file path that does not exist.
    while True:
        now = str(time()).replace(CON.period, '')
        path = Path(gettempdir()) / f'{CON.app_name}.{now}.txt'
        if not path.is_file():
            path = str(path)
            break

    # Write current text to it.
    with open(path, 'w') as fh:
        fh.write(text)

    # Let user edit the file.
    q = '"' if sys.platform == 'win32' else "'"
    cmd = f"{editor} {q}{path}{q}"
    p = run(cmd, shell = True)

    # Read file and return its edited text.
    if p.returncode == 0:
        with open(path) as fh:
            return fh.read()
    else:
        raise MvsError(MF.editor_cmd_nonzero.format(editor, path))

####
# Text wrapping and other string conversion utilities.
####

def underscores_to_hyphens(s):
    return s.replace(CON.underscore, CON.hyphen)

def hyphens_to_underscores(s):
    return s.replace(CON.hyphen, CON.underscore)

def hyphen_join(*xs):
    return CON.hyphen.join(filter(None, xs))

def with_newline(s):
    if s.endswith(CON.newline):
        return s
    else:
        return s + CON.newline

def indented(msg):
    if msg:
        return CON.newline.join(
            (CON.indent + line) if line.strip() else line
            for line in msg.split(CON.newline)
        )
    else:
        return ''

def para_join(*msgs):
    sep = CON.newline + CON.newline
    gen = (m.rstrip() for m in msgs)
    return sep.join(m for m in gen if m)

def wrap_text(text, width):
    # Takes some text and a max width.
    # Wraps the text to the desired width and returns it.

    # Convenience vars.
    NL = CON.newline
    SP = CON.space

    # Split text into words.
    words = [
        w
        for line in text.split(NL)
        for w in line.strip().split(SP)
    ]

    # Assemble the words into a list-of-list, where each
    # inner list will become a line within the width limit.
    lines = [[]]
    tot = 0
    for w in words:
        n = len(w)
        if n == 0:
            continue
        elif tot + n + 1 <= width:
            lines[-1].append(w)
            tot += n + 1
        else:
            lines.append([w])
            tot = n

    # Join the words back into a paragraph of text.
    return NL.join(
        SP.join(line)
        for line in lines
    )

####
# Validating user input.
####

def validated_choices(raw_input, choices):
    # Takes user input (str or sequence) and valid choices. Normalizes to
    # a tuple, validates the elements, and handles the "all" shortcut.
    # Return tuple or raises a ValueError.

    # Handle empty.
    if raw_input is None:
        return ()

    # Normalize to tuple.
    try:
        if isinstance(raw_input, str):
            xs = tuple(raw_input.split())
        else:
            xs = tuple(raw_input)
    except Exception:
        raise ValueError

    # Validate elements.
    if any(x not in choices for x in xs):
        raise ValueError

    # Return, with special handling for 'all'.
    if CON.all in xs:
        return tuple(x for x in choices if x != CON.all)
    else:
        uniq = []
        for x in xs:
            if x not in uniq:
                uniq.append(x)
        return tuple(uniq)

####
# Other.
####

def get_source_code(x):
    # Helper used to get source code for the
    # user-supplied renaming/filtering code.
    if callable(x):
        return getsource(x)
    else:
        return str(x)

