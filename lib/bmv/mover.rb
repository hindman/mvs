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
    )

    ####
    # Initialization.
    ####

    def initialize
      setup_options_parser
      @should_rename = nil
      @run_time = Time.now
    end

    def setup_options_parser
      # Defaults.
      @opts        = OpenStruct.new
      opts.rename  = 'path'
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
    # Run the renaming process.
    ####

    def run(kws = {})
      # Unpack input parameters.
      args  = kws.fetch(:args, [])
      stdin = kws.fetch(:stdin, $stdin)

      # Parse CLI options and get old paths.
      parse_options(args)
      handle_options
      process_stdin(stdin)

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

    def parse_options(args)
      # Parse CLI options and get any positional arguments.
      @cli_args = Array.new(args)
      @pos_args = Array.new(args)
      @parser.parse!(@pos_args)
    end

    def handle_options
      # Help.
      if opts.help
        puts @parser
        exit 0
      end

      # Create .bmv directory.
      if opts.init
        create_directory(log_dir)
        exit 0
      end

      # Quit if there is no .bmv directory.
      unless directory_exists(log_dir)
        msg = 'The .bmv directory does not exist. Run `bmv --init` to create it.'
        abort(msg)
      end

    end

    def process_stdin(stdin)
      # If the user did not supply positional arguments, get the old paths
      # from standard input.
      return unless pos_args.empty?
      @pos_args = stdin.map(&:chomp)
    end

    def initialize_renamings
      # Create the Renaming objects.
      @renamings = pos_args.map { |path| Bmv::Renaming.new(old_path: path) }
    end

    def set_new_paths
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
      puts to_yaml(brief = true)
      print "\nProceed? [y/n] "
      reply = $stdin.gets.chomp.downcase
      @should_rename = false unless reply == 'y'
    end

    def rename_files
      # Implement the renamings.
      return unless should_rename
      renamings.each { |r|
        # TODO.
        flag = r.should_rename ? 'Y' : 'n'
        puts "RENAME: #{flag}: #{r.old_path.path} -> #{r.new_path.path}"
      }
    end

    def write_log
      # Write the renaming data to a log file.
      File.open(log_path, 'w') { |fh| fh.write(to_yaml) }
    end

    def print_summary
      # Print summary information.
      h = {
        'n_paths'   => renamings.size,
        'n_renamed' => renamings.select(&:was_renamed).size,
        'log_file'  => log_path,
      }
      puts h.to_yaml
    end

    ####
    # The renamings as a data structure.
    ####

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
    # Miscellaneous helpers.
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

