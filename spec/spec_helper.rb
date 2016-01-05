$LOAD_PATH.unshift File.expand_path('../../lib', __FILE__)

require 'bmv'
require 'fileutils'
require 'open3'


module Bmv
  module SpecHelpers

    ####
    # Methods to manage the testing work area.
    ####

    PROJECT_ROOT = File.expand_path('../..', __FILE__)
    WORK_AREA_ROOT = File.join(PROJECT_ROOT, 'spec/work_area')

    def cd_to_work_area
      Dir.chdir(WORK_AREA_ROOT) { yield }
    end

    def clear_work_area
      # Deletes the contents of the testing work area.
      glob_pattern = File.join(WORK_AREA_ROOT, '*')
      contents = Dir.glob(glob_pattern)
      FileUtils::rm_rf(contents)
    end

    def read_work_area
      # Returns a sorted array of all files and directories in the work area.
      i = WORK_AREA_ROOT.size + 1
      glob_pattern = File.join(WORK_AREA_ROOT, '**/*')
      Dir.glob(glob_pattern).sort.map { |path| path[i..-1] }
    end

    def create_work_area(txt)
      # Takes some text and uses it to creates a directory tree
      # in the testing work area. See mover_spec.rb for examples.
      parse_work_area_text(txt).each { |line|
        path = File.join(WORK_AREA_ROOT, line)
        if path.end_with?('/')
          FileUtils::mkdir_p(path.chop)
        else
          FileUtils::touch(path)
        end
      }
    end

    def parse_work_area_text(txt)
      # Takes some text and parses into stripped, non-empty lines.
      txt.split("\n").map(&:strip).reject(&:empty?)
    end

    def sorted_work_area_text(txt)
      # Ditto, but sorts and removes trailing slashes.
      parse_work_area_text(txt).sort.map { |f| f.chomp('/') }
    end

    ####
    # Methods to run bmv and check its output.
    ####

    def bmv_cmd(arg_str)
      # Returns a command string to execute bmv.
      path = File.join(PROJECT_ROOT, 'bin/bmv')
      "bundle exec #{path} #{arg_str}".strip
    end

    def run_bmv(arg_str, parse = true)
      # Runs bmv with the given arguments string. Returns a hash of info.
      h = {
        :cmd  => bmv_cmd(arg_str),
        :data => {},
      }
      Open3.popen3(h[:cmd]) { |stdin, stdout, stderr, wait_thr|
        pstat = wait_thr.value    # A Process::Status instance.
        out = stdout.read()
        err = stderr.read()
        h.update({
          :stdout    => out,
          :stderr    => err,
          :pid       => pstat.pid,
          :exit_code => pstat.exitstatus,
        })
        h[:data] = YAML.load(out) if parse && h[:stdout].size > 0
      }
      return h
    end

    def check_bmv_data(bmv_data, exp_n_paths, exp_n_renamed)
      # Takes a hash from a bmv run and makes assertions about the counts.
      d = bmv_data[:data]
      expect(d['n_paths']).to eql(exp_n_paths)
      expect(d['n_renamed']).to eql(exp_n_renamed)
      # expect(d['log_file']).to be_a(String)
    end

  end
end


RSpec.configure do |c|
  c.include Bmv::SpecHelpers
end

