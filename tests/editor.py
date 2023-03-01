####
# An command-line "editor" used during testing.
#
# Takes path of input file of original paths.
#
# Rewrites the file to contain those paths plus the same
# paths having a .new suffix.
####

import sys

# The temp file path.
path = sys.argv[1]

# Read input paths.
origs = (line.strip() for line in open(path))
origs = list(filter(None, origs))

# Create new paths.
news = [o + '.new' for o in origs]

# Rewrite file.
with open(path, 'w') as fh:
    text = '\n'.join(origs + news)
    fh.write(text)

