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

    def initialize
      setup_parser
      @should_rename = false
      @run_time = Time.now
    end

    def setup_parser
      # Set defaults.
      @opts        = OpenStruct.new
      opts.dryrun  = false
      opts.confirm = false
      opts.help    = false
      opts.init    = false

      @parser = OptionParser.new do |p|

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

      end
    end

    def run(kws = {})

      args  = kws.fetch(:args, [])
      stdin = kws.fetch(:stdin, $stdin)

      parse_options(args)
      handle_options
      process_stdin(stdin)

      initialize_renamings
      set_new_paths

      check_for_missing_old_paths
      check_for_unchanged_paths
      check_for_new_path_duplicates
      check_for_clobbers
      check_for_missing_new_dirs

      handle_diagnostics
      get_confirmation
      rename_files
      write_log
      print_summary

    end

    def parse_options(args)
      @cli_args = Array.new(args)
      @pos_args = Array.new(args)
      @parser.parse!(@pos_args)
    end

    def handle_options
      if opts.help
        puts @parser
        exit 0
      end
      if opts.init
        FileUtils::mkdir_p(log_dir)
        exit 0
      end
      unless File.directory?(log_dir)
        msg = 'The .bmv directory does not exist. Run `bmv --init` to create it.'
        abort(msg)
      end
    end

    def process_stdin(stdin)
      return unless pos_args.empty?
      @pos_args = stdin.map(&:chomp)
    end

    def initialize_renamings
      @renamings = pos_args.map { |path| Bmv::Renaming.new(old_path: path) }
    end

    def set_new_paths
      renaming_code = %Q[
        def compute_new_path
          #{opts.rename}
        end
      ]
      Bmv::Renaming.send(:class_eval, renaming_code)
      renamings.each { |r|
        r.new_path = r.compute_new_path()
      }
    end

    def check_for_missing_old_paths
      renamings.each { |r|
        path = r.old_path.path
        r.diagnostics.add(:missing) unless path_exists(path)
      }
    end

    def check_for_unchanged_paths
      renamings.each { |r|
        r.diagnostics.add(:unchanged) if r.old_path.path == r.new_path.path
      }
    end

    def check_for_new_path_duplicates
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
      renamings.each { |r|
        path = r.new_path.path
        r.diagnostics.add(:clobber) if path_exists(path)
      }
    end

    def check_for_missing_new_dirs
      renamings.each { |r|
        path = r.new_path.directory
        r.diagnostics.add(:directory) unless directory_exists(path)
      }
    end

    def handle_diagnostics
      fatal = Set.new([:duplicate, :clobber, :directory])
      renamings.each { |r|
        ds = r.diagnostics
        if ds.empty?
          r.should_rename = true
        elsif (ds & fatal).empty?
          r.should_rename = false
        else
          r.should_rename = false
          @should_rename = true
        end
      }
    end

    def get_confirmation
      return unless opts.confirm
      puts to_yaml(brief = true)
      print "\nProceed? [y/n] "
      reply = $stdin.gets.chomp.downcase
      @should_rename = false unless reply == 'y'
    end

    def rename_files
      return unless should_rename
      renamings.each { |r|
        flag = r.should_rename ? 'Y' : 'n'
        puts "RENAME: #{flag}: #{r.old_path.path} -> #{r.new_path.path}"
      }
    end

    def write_log
      File.open(log_path, 'w') { |fh| fh.write(to_yaml) }
    end

    def print_summary
      h = {
        'n_paths'   => renamings.size,
        'n_renamed' => renamings.select(&:was_renamed).size,
        'log_file'  => log_path,
      }
      puts h.to_yaml
    end

    # def to_json(brief = false)
    #   h = to_h(brief = brief)
    #   JSON.pretty_generate(h, indent: '  ')
    # end

    def to_yaml(brief = false)
      h = to_h(brief = brief)
      h.to_yaml
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

    def path_exists(path)
      File.exist?(path)
    end

    def directory_exists(path)
      File.directory?(path)
    end

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

  end
end

