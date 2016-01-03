require 'spec_helper'

describe Bmv::Mover do

  # TODO: maybe use around(:example)
  #
  # around(:example) do
  #   Dir.chdir(WORK_AREA_ROOT) do
  #     clear_work_area
  #     yield
  #     clear_work_area
  #   end
  # end
  #
  # That will allow the bmv runs to be written naturally, without
  # worrying about WORK_AREA_ROOT at all.
  #
  # If I make this change, adjust create_work_area() accordingly.
  #   - if cwd is already WORK_AREA_ROOT, don't add prefix

  before(:example) {
    clear_work_area
  }

  after(:example) {
    clear_work_area
  }

  let(:ex1) {
    %q{
      d1/
      d1/f1
      d1/f2.txt

      d2/
      d2/f3.txt
      d2/f4.mp3
      d2/f5.mp3

      d3/
      d3/f6.txt
      d3/f7a.txt
      d3/f7b.mp3
    }
  }

  let(:ex1_parsed) {
    %w{
      d1/
      d1/f1
      d1/f2.txt
      d2/
      d2/f3.txt
      d2/f4.mp3
      d2/f5.mp3
      d3/
      d3/f6.txt
      d3/f7a.txt
      d3/f7b.mp3
    }
  }

  context 'scenarios' do

    it '#parse_work_area_text' do
      expect(parse_work_area_text(ex1)).to eql(ex1_parsed)
    end

    it 'todo' do
      # create_work_area(ex1)
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

