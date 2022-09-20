import pytest

from bmv import (
    version,
)

def test_version(tr):
    assert isinstance(version.__version__, str)

