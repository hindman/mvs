from .constants import CON

####
# Type validating functions given to argparse.
####

def positive_int(x):
    if x.isdigit():
        x = int(x)
        if x >= 1:
            return x
    raise ValueError

####
# A class to hold configuration information for each argparse argument.
#
# These instances are also by the mvs library to validate user-preferences
# and to merge preferences with command-line arguments.
####

class OptConfig:

    def __init__(self,
                 group = None,
                 names = None,
                 validator = None,
                 real_default = None,
                 **params):
        # Whether start a new argparse group before calling add_argument().
        self.group = group

        # The names supplied to add_argument(): eg, ('--help', '-h').
        # And the corresponding opt name: eg, 'help'.
        self.names = names.split()
        self.name = self.names[0].lstrip(CON.hyphen)

        # All other keyword parameters passed to add_argument().
        self.params = params

        # Whether the opt is a flag. We use this to set the argparse
        # choices setting for the --disable option.
        self.is_flag = params.get('action', None) == 'store_true'

        # An object used to validate user-preferences. See check_value().
        self.validator = validator

        # When configuring argparse, we always supply "empty" defaults (False,
        # None, or []). After we get opts from argparse, if an opt still has an
        # empty value, we know the user did not supply anything on the command
        # line -- which means we can safely apply either the real_default or a
        # value from user preferences.
        self.real_default = real_default

    def check_value(self, val):
        # If the validator is already a type (bool, int, etc), just
        # check the value's type and return None or the expected type name.
        # Otherwise, the validator is one of the staticmethod validator
        # functions defined in OptConfig. Those function behave in a
        # similar fashion: None for OK, str with expected type for invalid.
        f = self.validator
        if isinstance(f, type):
            if isinstance(val, f):
                return None
            else:
                return f.__name__
        else:
            return f(val)

    @staticmethod
    def posint(x):
        ok = (
            isinstance(x, int) and
            x >= 1 and
            not isinstance(x, bool)
        )
        if ok:
            return None
        else:
            return 'positive int'

    @staticmethod
    def list_of_str(xs):
        if isinstance(xs, list) and all(isinstance(x, str) for x in xs):
            return None
        else:
            return 'list[str]'

