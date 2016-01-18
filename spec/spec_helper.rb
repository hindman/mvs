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
      return Dir.glob(glob_pattern).sort.map { |path| path[i..-1] }
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
      return txt.split("\n").map(&:strip).reject(&:empty?)
    end

    def sorted_work_area_text(txt)
      # Ditto, but sorts and removes trailing slashes.
      return parse_work_area_text(txt).sort.map { |f| f.chomp('/') }
    end

    ####
    # Methods to run bmv and check its output.
    ####

    def bmv_cmd(arg_str)
      # Returns a command string to execute bmv.
      path = File.join(PROJECT_ROOT, 'bin/bmv')
      return "bundle exec #{path} #{arg_str}".strip
    end

    def run_bmv(arg_str, parse = true)
      # Runs bmv with the given arguments string. Returns a hash of info.
      h = {
        :cmd       => bmv_cmd(arg_str),
        :stdout    => nil,
        :stderr    => nil,
        :pid       => nil,
        :exit_code => nil,
        :data      => nil,
      }
      Open3.popen3(h[:cmd]) { |stdin, stdout, stderr, wait_thr|
        # Collect output.
        out = stdout.read()
        err = stderr.read()

        # Get the Process::Status instance, and its PID and exit code.
        # In Ruby 1.8.7 popen3 does not provide wait_thr.
        pstat = wait_thr.nil? ? $? : wait_thr.value
        pid = pstat.pid
        exit_code = pstat.exitstatus

        # Update the info hash.
        h.update({
          :stdout    => out,
          :stderr    => err,
          :pid       => pid,
          :exit_code => exit_code,
          :data      => (parse && out.size > 0) ? YAML.load(out) : {},
        })
      }
      return h
    end

    def check_bmv_data(bmv_data, exp_n_paths, exp_n_renamed, exp_stderr)
      # Takes a hash from a bmv run and makes assertions about the counts.
      d = bmv_data[:data]
      expect(bmv_data[:stderr]).to eql(exp_stderr)
      expect(d['n_paths']).to eql(exp_n_paths)
      expect(d['n_renamed']).to eql(exp_n_renamed)
      # expect(d['log_file']).to be_a(String)
    end

  end
end


RSpec.configure do |c|

  # So we can call helper methods directly in our Rspec tests.
  c.include Bmv::SpecHelpers

  # Create the .bmv work directory if it doesn't exist.
  c.before(:suite) {
    Class.new.extend(Bmv::SpecHelpers).run_bmv('--init')
  }

end

