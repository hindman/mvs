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
      :exit_code
    )

    EXIT_CODES = {
      :ok                => 0,
      :no_bmv_dir        => 1,
      :invalid_n_paths   => 2,
      :failed_diagnostic => 3,
      :no_confirmation   => 4,
    }

    ####
    # Initialization.
    ####

    def initialize
      @opts = default_options()
      @parser = options_parser()
      @should_rename = nil
      @run_time = Time.now
      @streams = nil
      @exit_code = nil
    end

    def default_options
      o         = OpenStruct.new
      o.rename  = nil
      o.pairs   = false
      o.concat  = false
      o.stdin   = false
      o.dryrun  = false
      o.prompt  = false
      o.help    = false
      o.verbose = false
      o.init    = false
      return o
    end

    def options_parser
      return OptionParser.new { |p|

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

        p.on('--stdin', 'Supply paths via standard input') {
          opts.stdin = true
        }

        p.on('--dryrun', '--dry-run', '--dry_run', 'Dryrun mode') {
          opts.dryrun = true
        }

        p.on('--prompt', 'Prompt for user confirmation before renaming') {
          opts.prompt = true
        }

        # Other options.
        p.separator ''
        p.separator 'Other options:'

        p.on('-h', '--help', 'Show this message') {
          opts.help = true
        }

        p.on('--verbose', 'Print more renaming information') {
          opts.verbose = true
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
      # TODO: should validate kws.
      args = kws.fetch(:args, [])
      @streams = {
        :stdout => kws.fetch(:stdout, $stdout),
        :stderr => kws.fetch(:stderr, $stderr),
        :stdin  => kws.fetch(:stdin,  $stdin),
      }

      # Parse CLI options and get old paths.
      parse_cli_args(args)
      handle_special_options
      process_stdin
      validate_cli_args

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
      prompt_for_confirmation

      # Implement the renaming and write output.
      rename_files
      write_log
      print_summary
      quit(exit_code, nil)
    end

    ####
    # The renaming process: options and old paths.
    ####

    def parse_cli_args(args)
      # Parse CLI options and get any positional arguments.
      @cli_args = Array.new(args)
      @pos_args = Array.new(args)
      parser.parse!(pos_args)
      # If the user supplied the conventional argument for stdin,
      # make the needed adjustments. We will read from stdin
      # after checking for special options.
      if pos_args == ['-']
        pos_args.pop
        opts.stdin = true
      end
    end

    def handle_special_options
      # Help.
      if opts.help
        quit(:ok, parser.to_s)
      end

      # Create .bmv directory.
      if opts.init
        create_directory(log_dir)
        msg = "Created directory: #{bmv_dir}"
        quit(:ok, msg)
      end

      # Quit if there is no .bmv directory.
      unless directory_exists(log_dir)
        msg = 'The .bmv directory does not exist. Run `bmv --init` to create it.'
        quit(:no_bmv_dir, msg)
      end
    end

    def process_stdin
      @pos_args = streams[:stdin].map(&:chomp) if opts.stdin
    end

    def validate_cli_args
      # Input paths cannot be empty strings.
      @pos_args = pos_args.reject(&:empty?)

      # Input paths: require at least 1.
      if pos_args.size < 1
        msg = 'At least one input path is required.'
        quit(:invalid_n_paths, msg)
      end

      # Input paths: require even number with some options.
      if pos_args.size.odd?
        if opts.pairs || opts.concat
          msg = 'An even number of input paths is required for --pairs and --concat.'
          quit(:invalid_n_paths, msg)
        end
      end
    end

    ####
    # The renaming process: renaming instances and their paths.
    ####

    def initialize_renamings
      # Create the Renaming objects.
      @renamings = positional_indexes.map { |i, j|
        old_path = pos_args[i]
        new_path = pos_args[j]
        Bmv::Renaming.new(old_path, new_path)
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
      n = 0
      @should_rename = true
      renamings.each { |r|
        ds = r.diagnostics
        if (ds & fatal).empty?
          # No fatal problems, but we might want to skip this renaming.
          if ds.empty?
            r.should_rename = true
            n += 1
          else
            r.should_rename = false
          end
        else
          # Fatal problem.
          r.should_rename = false
          @should_rename = false
          @exit_code = :failed_diagnostic
        end
      }
      if n < 1
        @should_rename = false
        @exit_code = :failed_diagnostic
      end
    end

    def prompt_for_confirmation
      # Get user confirmation, if needed.
      return unless opts.prompt
      return unless should_rename
      say(to_yaml(brief = true))
      say("\nProceed? [y/n] ", :write)
      reply = streams[:stdin].gets.chomp.downcase
      if reply == 'y'
        @should_rename = true
      else
        @should_rename = false
        @exit_code = :no_confirmation
      end
    end

    ####
    # The renaming process: rename and produce output.
    ####

    def rename_files
      # Implement the renamings.
      renamings.each { |r|
        if should_rename && r.should_rename
          FileUtils.mv(r.old_path.path, r.new_path.path)
          r.was_renamed = true
        else
          r.was_renamed = false
        end
      }
      @exit_code = :ok if exit_code.nil?
    end

    def write_log
      # Write the renaming data to a log file.
      write_file(log_path, to_yaml)
    end

    def print_summary
      # Print summary information.
      h = summary
      h.update(to_h) if opts.verbose
      say(h.to_yaml)
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
        return (0...size).step(2).map { |i| [i, i + 1] }
      elsif opts.concat
        return (0...half).map { |i| [i, i + half] }
      else
        return (0...size).map { |i| [i, i] }
      end
    end

    def summary
      return {
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
          'exit_code'     => exit_code.to_s,
          'bmv_version'   => Bmv::VERSION,
        }
      end
    end

    def to_yaml(brief = false)
      h = to_h(brief = brief)
      return h.to_yaml
    end

    ####
    # Helpers: paths to bmv directories and logs.
    ####

    def bmv_dir
      return File.join(File.expand_path('~'), '.bmv')
    end

    def log_dir
      return File.join(bmv_dir, 'logs')
    end

    def log_path
      file_name = run_time.strftime('%Y_%m_%d_%H_%M_%S_%L') + '.yaml'
      return File.join(log_dir, file_name)
    end

    ####
    # Side-effects: interaction with file system, printing, exiting, etc.
    ####

    def quit(code, msg)
      stream = code == :ok ? streams[:stdout] : streams[:stderr]
      stream.puts(msg) unless msg.nil?
      Kernel.exit(EXIT_CODES.fetch(code, 999))
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

