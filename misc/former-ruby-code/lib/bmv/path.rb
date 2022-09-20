require 'pathname'

module Bmv
  class Path

    # A simple data class to hold a path to a file or directory
    # and the various components of the path. User code does
    # not interact directly with these intances.

    attr_accessor(
      :path,
      :directory,
      :file_name,
      :extension,
      :stem
    )

    def initialize(path)                     # Example 1           Example 2
      @path      = Pathname.new(path)        # foo/bar/fubb.txt    blah
      @directory = @path.dirname()           # foo/bar             .
      @file_name = @path.basename()          #         fubb.txt    blah
      @extension = @path.extname()           #             .txt    ''
      @stem      = @path.basename(extension) #         fubb        blah
    end

  end
end

