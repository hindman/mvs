$LOAD_PATH.unshift File.expand_path('../../lib', __FILE__)

require 'bmv'
require 'fileutils'


module Bmv
  module SpecHelpers

    # TODO: define this relative the to path of the current file.
    WORK_AREA_ROOT = 'spec/work_area'

    def parse_work_area_text(txt)
      # Text some text and parses into striped, non-empty lines.
      txt.split("\n").map(&:strip).reject(&:empty?)
    end

    def create_work_area(txt)
      # Creates a directory tree in the testing work area.
      parse_work_area_text(txt).each { |line|
        path = File.join(WORK_AREA_ROOT, line)
        if path.end_with?('/')
          FileUtils::mkdir_p(path.chop)
        else
          FileUtils::touch(path)
        end
      }
    end

    def clear_work_area
      # Deletes the testing work area.
      FileUtils::rm_rf(WORK_AREA_ROOT)
    end

  end
end


RSpec.configure do |c|
  c.include Bmv::SpecHelpers
end

