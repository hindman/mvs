
class RenamingPlan:

    def __init__(self,
                 inputs,
                 rename_code,
                 structure = None,
                 seq_start = 1,
                 seq_step = 1,
                 skip_equal = False,
                 filter_code = None,
                 indent = 4,
                 file_sys = None):

        # Add validation. Convert to attrs.
        self.inputs = tuple(inputs)
        self.rename_code = rename_code
        self.structure = structure
        self.seq_start = seq_start
        self.seq_step = seq_step
        self.skip_equal = skip_equal
        self.filter_code = filter_code
        self.indent = indent
        self.file_sys = file_sys

    def prepare(self):
        pass

