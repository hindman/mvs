from bmv import __version__

def test_version(tr):
    # Confirm that we can import __version__ from bmv package.
    assert isinstance(__version__, str)

