import pytest

# Import these directly from the package.
from mvs import RenamingPlan, MvsError, __version__

from mvs.utils import (
    indented,
    para_join,
    validated_choices,
    with_newline,
    wrap_text,
)

def test_top_level_imports(tr):
    # Exercise the package's top-level importables.
    # Do something simple with each one.
    assert 'a' in RenamingPlan(inputs = ('a', 'b')).inputs
    assert MvsError('foo', x = 1).msg == 'foo'
    assert isinstance(__version__, str)

def test_with_newline(tr):
    txt = 'foo'
    exp = txt + '\n'
    assert with_newline(txt) == exp
    assert with_newline(exp) == exp

def test_indented(tr):
    # Basic usage.
    txt = 'x1\nx2\nx3'
    exp = txt.replace('x', '  x')
    got = indented(txt)
    assert got == exp

    # Lines without non-whitespace characters are not indented.
    txt = 'x1\nx2\n  \nx3'
    exp = txt.replace('x', '  x')
    got = indented(txt)
    assert got == exp

    # Empty text is unchanged.
    txt = ''
    got = indented(txt)
    assert got == txt

def test_wrap_text(tr):
    # Basic usage: text is split on single spaces; empty
    # words are filtered out; words are rejoined on single
    # spaces and assembled into lines fitting the width limit.
    txt = (
        'Assemble the words   into a list-of-list, where each '
        'inner list will   become a super-long-word-beyond-limit line within the width limit.'
    )
    exp = (
        'Assemble the words\n'
        'into a list-of-list,\n'
        'where each inner\n'
        'list will become a\n'
        'super-long-word-beyond-limit\n'
        'line within the\n'
        'width limit.'
    )
    got = wrap_text(txt, 20)
    assert got == exp

def test_para_join(tr):
    # Paragraphs are right-stripped; empties filtered out; then joined.
    paras = ('x1', '  ', 'x2', '', 'x3')
    exp = 'x1\n\nx2\n\nx3'
    got = para_join(*paras)
    assert got == exp

def test_validated_choices(tr):
    choices = ('A', 'B', 'C', 'D', 'E', 'all')

    # Basic usage: input can be str, tuple, or list. If values are among
    # the valid choices, they are return as a de-duplicated tuple.
    variations = (
        'A C',
        'A C A',
        ('A', 'C'),
        ['A', 'A', 'C'],
    )
    exp = ('A', 'C')
    for v in variations:
        assert validated_choices(v, choices) == exp

    # The 'all' shortcut.
    exp = choices[:-1]
    assert validated_choices('all', choices) == exp
    assert validated_choices('A all C', choices) == exp

    # Completely invalid input.
    with pytest.raises(ValueError):
        validated_choices(3.14, choices)

    # Input with an invalid value.
    with pytest.raises(ValueError):
        validated_choices('A C fubb', choices)

