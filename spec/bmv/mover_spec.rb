=begin



pos_args via stdin
pos_args with empty strings
no pos_args

help option
mising bmv directory
init option

pairs option
concat option
pairs and concat options with odd N args

dryrun option

prompt option

confirm log file is written

prompt_for_confirmation()

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

=end

require 'spec_helper'

describe Bmv::Mover do

  around(:example) { |example|
    clear_work_area
    cd_to_work_area(&example)
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

  it '#parse_work_area_text' do
    got = parse_work_area_text(ex1)
    exp = %w{
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
    expect(got).to eql(exp)
  end

  context 'Scenarios' do

    it 'basic' do
      create_work_area(ex1)
      h = run_bmv(%q{*/*.txt --rename 'path.sub /f/, "G___G"'})
      got = read_work_area()
      exp = sorted_work_area_text(%q{
        d1/
        d1/f1
        d1/G___G2.txt
        d2/
        d2/G___G3.txt
        d2/f4.mp3
        d2/f5.mp3
        d3/
        d3/G___G6.txt
        d3/G___G7a.txt
        d3/f7b.mp3
      })
      expect(got).to eql(exp)
      check_bmv_data(h, 4, 4)
    end

  end

end

