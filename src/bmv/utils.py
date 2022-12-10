import subprocess

from .data_objects import OptsFailure
from .constants import CON, CONTROLLABLES, FAIL

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

def validated_failure_controls(x, opts_mode = False):
    # Takes either the parsed command-line options (opts) or a RenamingPlan
    # instance. Processes the failure-control attributes of that object.
    #
    # Builds a dict mapping each Failure class that the user wants to control
    # to a (CONTROL, NAME) tuple.
    #
    # Returns either a simplified version of that dict or a Failure,
    # the latter in the case of contradictory configurations by the user.

    # Converts a name to an option: eg, 'skip_equal' to '--skip-equal'.
    name_to_opt = lambda nm: CON.dash + nm.replace(CON.underscore, CON.hyphen)

    # Build the failure-control dict.
    config = {}
    for name2, (control, fail_cls) in CONTROLLABLES:
        # If X has a true value for the attribute, we need to deal with it.
        if getattr(x, name2, None):
            if fail_cls in config:
                # If the failure-class is already in the failure-control
                # dict, the user has attempted to set two different
                # controls for the same failure type. Return a Failure.
                (_, name1) = config[fail_cls]
                if opts_mode:
                    name1, name2 = (name_to_opt(name1), name_to_opt(name2))
                msg = FAIL.conflicting_controls.format(name1, name2)
                return OptsFailure(msg)
            else:
                # No problem: add an entry to the dict.
                config[fail_cls] = (control, name2)

    # Return a simplified variant of the dict.
    d = {
        fail_cls : control
        for fail_cls, (control, name) in config.items()
    }
    return d

