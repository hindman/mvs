require 'spec_helper'

describe Bmv::Mover do

  let(:x) { 42 }

  context 'todo' do

    it 'todo' do
      expect(x).to eql(42)
    end

  end

end

__END__

Primary testing:

  end-to-end calls to run()
    - using real files
    - asserting against @renamings and/or to_h
    - sometimes asserting against renamed files themselves

  need a couple of utility functions
    - create a directory tree (old_paths)
    - check a directory tree (renamed stuff)

Special testing:

  pos_args
    via args
    via stdin

  special options
    help
    init
    missing bmv_dir

  get_confirmation

  confirm log file is written

  check print summary

Notes for mocking, if needed:

  stdin
    map
    gets

  stderr
    puts

  stdout
    puts
    write

  quit
    streams
    exit

  say
    streams

  handle_options
    quit

  get_confirmation
    say
    streams

  process_stdin
    streams

  rename_files
    rename, etc.

  print_summary
    say

