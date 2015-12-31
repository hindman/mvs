module Bmv
  class Renaming

    attr_accessor(
      :old_name,
      :new_name,
      :new_dir,
      :onm,
      :nnm,
      :ndir,
      :diagnostics,
      :should_rename,
    )

    def initialize(kws = {})
      @old_name = kws.fetch(:old_name, nil)
      @new_name = kws.fetch(:new_name, nil)
      @new_dir  = kws.fetch(:new_dir, nil)
      @diagnostics = Set.new
      @should_rename = nil
    end

    def to_s
      "#<Renaming old_name=#{old_name}, new_name=#{new_name}"
    end

    def onm
      old_name
    end

    def nnm
      new_name
    end

    def ndir
      new_dir
    end

  end
end

