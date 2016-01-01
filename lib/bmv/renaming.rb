module Bmv
  class Renaming

    attr_reader(
      :old_path,
      :new_path,
    )

    attr_accessor(
      :diagnostics,
      :should_rename,
      :was_renamed,
    )

    def initialize(kws = {})
      self.old_path  = kws.fetch(:old_path, nil)
      self.new_path  = kws.fetch(:new_path, nil)
      @diagnostics   = Set.new
      @should_rename = nil
      @was_renamed   = nil
    end

    ####
    # Setters for the old and new paths.
    ####

    def old_path=(path)
      @old_path = make_path(path)
    end

    def new_path=(path)
      @new_path = make_path(path)
    end

    def make_path(path)
      path.nil? ? nil : Bmv::Path.new(path)
    end

    ####
    # The Renaming as either a string or hash.
    ####

    def to_s
      "#<Renaming old_path=#{old_path.path}, new_path=#{new_path.path}"
    end

    def to_h(brief = false)
      h = {
        'old_path'      => old_path.path.to_s,
        'new_path'      => new_path.path.to_s,
        'diagnostics'   => diagnostics.map(&:to_s).sort,
        'should_rename' => should_rename,
        'was_renamed'   => was_renamed,
      }
      if brief
        h.delete('diagnostics')
        h.delete('should_rename')
        h.delete('was_renamed')
      end
      return h
    end

    ####
    # Convenience methods to get file name components from the old_path.
    # These are intended to be used in the user-supplied renaming code.
    ####

    def p    ; old_path.path.to_s      ; end
    def d    ; old_path.directory.to_s ; end
    def f    ; old_path.file_name.to_s ; end
    def s    ; old_path.stem.to_s      ; end
    def e    ; old_path.extension.to_s ; end

    def path ; old_path.path.to_s      ; end
    def dir  ; old_path.directory.to_s ; end
    def file ; old_path.file_name.to_s ; end
    def stem ; old_path.stem.to_s      ; end
    def ext  ; old_path.extension.to_s ; end

  end
end

