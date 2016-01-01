require 'ostruct'
require 'optparse'
require 'set'
require 'yaml'
require 'fileutils'

module Bmv
  class Mover

    attr_accessor(
      :opts,
      :parser,
      :cli_args,
      :pos_args,
      :renamings,
      :should_rename,
      :run_time,
      :streams,
    )

    ####
    # Initialization.
    ####

    def initialize
      setup_options_parser
      @should_rename = nil
      @run_time = Time.now
      @streams = nil
    end

    def setup_options_parser
      # Defaults.
      @opts        = OpenStruct.new
      opts.rename  = nil
      opts.pairs   = false
      opts.concat  = false
      opts.dryrun  = false
      opts.confirm = false
      opts.help    = false
      opts.init    = false

      # Create the option parser.
      @parser = OptionParser.new { |p|

        # Banner.
        p.banner = 'Usage: bmv [options] [ORIG_FILES]'

        # Main options.
        p.separator ''
        p.separator 'Main options:'

        p.on('-r', '--rename CODE') { |c|
          opts.rename = c
        }

        p.on('--pairs', 'Supply old and new paths in pairwise fashion') {
          opts.pairs = true
        }

        p.on('--concat', 'Supply old and new paths in concatenated fashion') {
          opts.concat = true
        }

        p.on('--dryrun', '--dry-run', '--dry_run', 'Dryrun mode') {
          opts.dryrun = true
        }

        p.on('--confirm', 'Get user confirmation before renaming') {
          opts.confirm = true
        }

        # Other options.
        p.separator ''
        p.separator 'Other options:'

        p.on('-h', '--help', 'Show this message') {
          opts.help = true
        }

        p.on('--init', 'Create the .bmv directory') {
          opts.init = true
        }

      }
    end

    ####
    # The renaming process: run()
    ####

    def run(kws = {})
      # Unpack input parameters.
      args = kws.fetch(:args, [])
      @streams = {
        stdout: kws.fetch(:stdout, $stdout),
        stderr: kws.fetch(:stderr, $stderr),
        stdin:  kws.fetch(:stdin,  $stdin),
      }

      # Parse CLI options and get old paths.
      parse_options(args)
      handle_special_options
      process_stdin
      handle_normal_options

      # Create the Renaming instances, with both old_path and new_path.
      initialize_renamings
      set_new_paths

      # Run various checks. If adverse conditions are detected, diagnostic
      # codes are added to the applicable Renaming instances.
      check_for_missing_old_paths
      check_for_unchanged_paths
      check_for_new_path_duplicates
      check_for_clobbers
      check_for_missing_new_dirs

      # Decide whether to proceed with any renamings.
      handle_diagnostics
      get_confirmation

      # Implement the renaming and write output.
      rename_files
      write_log
      print_summary
    end

    ####
    # The renaming process: options and old paths.
    ####

    def parse_options(args)
      # Parse CLI options and get any positional arguments. If the user did not
      # supply positional arguments, get the input paths from standard input.
      @cli_args = Array.new(args)
      @pos_args = Array.new(args)
      @parser.parse!(@pos_args)
    end

    def handle_special_options
      # Help.
      if opts.help
        quit(0, parser.to_s)
      end

      # Create .bmv directory.
      if opts.init
        create_directory(log_dir)
        msg = "Created directory: #{bmv_dir}"
        quit(0, msg)
      end

      # Quit if there is no .bmv directory.
      unless directory_exists(log_dir)
        msg = 'The .bmv directory does not exist. Run `bmv --init` to create it.'
        quit(1, msg)
      end

    end

    def process_stdin
      @pos_args = streams[:stdin].map(&:chomp) if pos_args.empty?
    end

    def handle_normal_options
      # Input paths: require at least 1.
      if pos_args.size < 1
        msg = 'At least one input path is required.'
        quit(1, msg)
      end

      # Input paths: require even number with some options.
      if pos_args.size.odd?
        if opts.pairs || opts.concat
          msg = 'An even number of input paths is required for --pairs and --concat.'
          quit(1, msg)
        end
      end
    end

    ####
    # The renaming process: renaming instances and their paths.
    ####

    def initialize_renamings
      # Create the Renaming objects.
      @renamings = positional_indexes.map { |i, j|
        op = pos_args[i]
        np = pos_args[j]
        Bmv::Renaming.new(old_path: op, new_path: np)
      }
    end

    def set_new_paths
      return if opts.pairs
      return if opts.concat
      return if opts.rename.nil?
      # Use the user-supplied code to add a method to the Renaming class.
      renaming_code = %Q[
        def compute_new_path
          #{opts.rename}
        end
      ]
      Bmv::Renaming.send(:class_eval, renaming_code)
      # Execute that method to create the new paths.
      renamings.each { |r|
        r.new_path = r.compute_new_path()
      }
    end

    ####
    # The renaming process: diagnostics.
    ####

    def check_for_missing_old_paths
      # The old paths should exist.
      renamings.each { |r|
        path = r.old_path.path
        r.diagnostics.add(:missing) unless path_exists(path)
      }
    end

    def check_for_unchanged_paths
      # The new path and old path should differ.
      renamings.each { |r|
        r.diagnostics.add(:unchanged) if r.old_path.path == r.new_path.path
      }
    end

    def check_for_new_path_duplicates
      # The new paths should not have any duplicates.
      univ = Hash.new{ |h, k| h[k] = [] }
      renamings.each { |r|
        path = r.new_path.path
        univ[path].push(r)
      }
      renamings.each { |r|
        path = r.new_path.path
        r.diagnostics.add(:duplicate) if univ[path].size > 1
      }
    end

    def check_for_clobbers
      # The new paths should not clobber existing paths.
      renamings.each { |r|
        path = r.new_path.path
        r.diagnostics.add(:clobber) if path_exists(path)
      }
    end

    def check_for_missing_new_dirs
      # The directories of the new paths should exist.
      renamings.each { |r|
        path = r.new_path.directory
        r.diagnostics.add(:directory) unless directory_exists(path)
      }
    end

    ####
    # The renaming process: decide what to rename.
    ####

    def handle_diagnostics
      # Evaluate the diagnostics to determine whether to proceed at all and, if
      # so, which paths to rename. Those decisions are held in the
      # should_rename attribute of both the individual Renaming instances and
      # in the overall Mover instance.
      fatal = Set.new([:duplicate, :clobber, :directory])
      @should_rename = true
      renamings.each { |r|
        ds = r.diagnostics
        if (ds & fatal).empty?
          r.should_rename = ds.empty?
        else
          r.should_rename = false
          @should_rename = false
        end
      }
    end

    def get_confirmation
      # Get user confirmation, if needed.
      return unless opts.confirm
      return unless should_rename
      say(to_yaml(brief = true))
      say("\nProceed? [y/n] ", :write)
      reply = streams[:stdin].gets.chomp.downcase
      @should_rename = false unless reply == 'y'
    end

    ####
    # The renaming process: rename and produce output.
    ####

    def rename_files
      # Implement the renamings.
      return unless should_rename
      renamings.each { |r|
        flag = r.should_rename ? 'Y' : 'n'
        r.was_renamed = r.should_rename
        say("RENAME: #{flag}: #{r.old_path.path} -> #{r.new_path.path}")
      }
    end

    def write_log
      # Write the renaming data to a log file.
      write_file(log_path, to_yaml)
    end

    def print_summary
      # Print summary information.
      say(summary.to_yaml)
    end

    ####
    # Data structures during the renaming process.
    ####

    def positional_indexes
      # Returns an array of index pairs. Each pair provide the indexes to get
      # an old_path and new_path from @pos_args. In the default case, the
      # old_path and new_path start out with the same value.
      size = pos_args.size
      half = size / 2
      if opts.pairs
        (0...size).step(2).map { |i| [i, i + 1] }
      elsif opts.concat
        (0...half).map { |i| [i, i + half] }
      else
        (0...size).map { |i| [i, i] }
      end
    end

    def summary
      {
        'n_paths'   => renamings.size,
        'n_renamed' => renamings.select(&:was_renamed).size,
        'log_file'  => log_path,
      }
    end

    def to_h(brief = false)
      if brief
        rs = renamings.select(&:should_rename).map { |r| r.to_h(brief) }
        return {'renamings' => rs}
      else
        return {
          'cli_args'      => cli_args,
          'renamings'     => renamings.map(&:to_h),
          'should_rename' => should_rename,
          'bmv_version'   => Bmv::VERSION,
        }
      end
    end

    def to_yaml(brief = false)
      h = to_h(brief = brief)
      h.to_yaml
    end

    ####
    # Helpers: paths to bmv directories and logs.
    ####

    def bmv_dir
      File.join(File.expand_path('~'), '.bmv')
    end

    def log_dir
      File.join(bmv_dir, 'logs')
    end

    def log_path
      file_name = run_time.strftime('%Y_%m_%d_%H_%M_%S') + '.yaml'
      File.join(log_dir, file_name)
    end

    ####
    # Side-effects: interaction with file system, printing, exiting, etc.
    ####

    def quit(code, msg)
      stream = code == 0 ? streams[:stdout] : streams[:stderr]
      stream.puts(msg) unless msg.nil?
      Kernel.exit(code)
    end

    def say(msg, meth = :puts)
      streams[:stdout].send(meth, msg)
    end

    def write_file(path, msg)
      File.open(path, 'w') { |fh| fh.write(msg) }
    end

    def path_exists(path)
      File.exist?(path)
    end

    def directory_exists(path)
      File.directory?(path)
    end

    def create_directory(path)
      FileUtils::mkdir_p(path)
    end

  end
end

