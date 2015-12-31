require "bmv/version"

module Bmv

  class BulkMover

    attr_accessor(
      :opts,
    )

    def initialize
      puts 'initialize()'
    end

    def run
      puts 'run()'
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

        # Other options.
        p.separator ''
        p.separator 'Other options:'

        p.on('-h', '--help', 'Show this message') do
          opts.help = true
          puts p
          exit
        end

      end
    end

  end

  class Renaming

    attr_accessor(
      :old_name,
      :new_name,
      :new_dir,
    )

  end

  class FileName
  end

  def self.twelve
    12
  end

end

