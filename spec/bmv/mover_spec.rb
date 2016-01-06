=begin

Confirm that failure scenarios are working:

  check_bmv_data(): enhance to check everything
      - exit code
      - stdout data
      - stderr data
      - dir tree
      - log file

  diagnostic: missing old paths
  diagnostic: unchanged paths (confirm data structure is correct)
  diagnostic: new path duplicates
  diagnostic: clobbers
  diagnostic: missing new dirs

  no pos_args
  pos_arg all empty

  pairs and concat options with odd N args

  mising bmv directory

Special options:
  help option
  init option

Renaming scenarios
  pos_args via stdin
  pos_args with some empty strings
  basic regex
  use every path element
    path
    dir
    file
    stem
    ext
  pairs option
  concat option

  check the following for each scenario:
    file sys
    to_h data
    log file is written
    print summary

  dryrun option: nothing should be renamed

  prompt option:
    - if no: nothing should be renamed
    - if yes: renamed stuff

Special unit tests:
  prompt_for_confirmation()
  positional_indexes()
  quit()


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

  context 'Failed diagnostics' do

    it 'missing old paths' do
      create_work_area(ex1)
      h = run_bmv(%q{--rename 'path.sub /b/, "B"'})
      got = read_work_area()
      exp = sorted_work_area_text(ex1)
      expect(got).to eql(exp)
      check_bmv_data(h, nil, nil)
    end

    it 'unchanged paths' do
    end

    it 'new path duplicates' do
    end

    it 'clobbers' do
    end

    it 'missing new dirs' do
    end

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

