require 'ostruct'
require 'optparse'

module Bmv
  class BulkMover

    attr_accessor(
      :opts,
      :parser,
      :args,
    )

    def initialize(kws = {})
      puts 'initialize()'
      args = kws.fetch(:args, nil)
      setup_parser
      parse_options(args) unless args.nil?
    end

    def run
      puts 'run()'
      puts "Options: #{opts}"
      puts "Args: #{args}"
    end

    def setup_parser

      puts 'setup_parser()'

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
          puts p
          exit
        }

      end
    end

    def parse_options(args)
      args = Array.new(args)
      @parser.parse!(args)
      @args = args
    end

  end
end

