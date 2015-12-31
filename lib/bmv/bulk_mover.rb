require 'ostruct'
require 'optparse'
require 'set'

module Bmv
  class BulkMover

    attr_accessor(
      :opts,
      :parser,
      :cli_args,
      :pos_args,
      :renamings,
      :errors,
      :should_halt,
    )

    def initialize
      setup_parser
      @errors = []
      @should_halt = false
    end

    def setup_parser
      # Set defaults.
      @opts       = OpenStruct.new
      opts.dryrun = false
      opts.help   = false

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

        # Other options.
        p.separator ''
        p.separator 'Other options:'

        p.on('-h', '--help', 'Show this message') {
          opts.help = true
        }

      end
    end

    def run(kws = {})

      args  = kws.fetch(:args, [])
      stdin = kws.fetch(:stdin, $stdin)

      parse_options(args)
      if opts.help
        puts @parser
        exit
      end
      process_stdin(stdin)

      initialize_renamings
      set_new_names

      check_for_unchanged_names
      check_for_new_name_duplicates
      check_for_clobbers
      check_for_missing_new_dirs

      handle_diagnostics
      rename_files

    end

    def parse_options(args)
      @cli_args = Array.new(args)
      @pos_args = Array.new(args)
      @parser.parse!(@pos_args)
    end

    def process_stdin(stdin)
      return unless pos_args.empty?
      @pos_args = stdin.map { |line| line.chomp }
    end

    def initialize_renamings
      @renamings = pos_args.map { |orig| Bmv::Renaming.new(old_name: orig) }
    end

    def set_new_names
      renaming_code = %Q[
        def compute_new_name
          #{opts.rename}
        end
      ]
      Bmv::Renaming.send(:class_eval, renaming_code)
      renamings.each { |r|
        r.new_name = r.compute_new_name()
      }
    end

    def check_for_unchanged_names
      renamings.each { |r|
        nm = r.new_name
        r.diagnostics.add(:unchanged) if nm == r.old_name
      }
    end

    def check_for_new_name_duplicates
      univ = Hash.new{ |h, k| h[k] = [] }
      renamings.each { |r|
        nm = r.new_name
        univ[nm].push(r)
      }
      renamings.each { |r|
        nm = r.new_name
        r.diagnostics.add(:duplicate) if univ[nm].size > 1
      }
    end

    def check_for_clobbers
      renamings.each { |r|
        nm = r.new_name
        r.diagnostics.add(:clobber) if file_exists(nm)
      }
    end

    def file_exists(path)
      File.exist?(path)
    end

    def check_for_missing_new_dirs
      # TODO
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
          @should_halt = true
        end
      }
    end

    def rename_files
      # TODO

      puts "HALT: #{should_halt}"
      renamings.each { |r|
        flag = r.should_rename ? 'Y' : 'n'
        puts "RENAME: #{flag}: #{r.old_name} -> #{r.new_name}"
      }

    end

  end
end

