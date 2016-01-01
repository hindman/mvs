require 'pathname'

module Bmv
  class Path

    attr_accessor(
      :path,
      :directory,
      :file_name,
      :extension,
      :stem,
    )

    def initialize(path)                     # Example 1           Example 2
      @path      = Pathname.new(path)        # foo/bar/fubb.txt    blah
      @directory = @path.dirname()           # foo/bar             .
      @file_name = @path.basename()          #         fubb.txt    blah
      @extension = @path.extname()           #             .txt    ''
      @stem      = @path.basename(extension) #         fubb        blah
    end

    # def p    ; path.to_s      ; end
    # def d    ; directory.to_s ; end
    # def f    ; file_name.to_s ; end
    # def s    ; stem.to_s      ; end
    # def e    ; extension.to_s ; end

    # def dir  ; directory.to_s ; end
    # def file ; file_name.to_s ; end
    # def ext  ; extension.to_s ; end

  end
end

