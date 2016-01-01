require 'spec_helper'

describe Bmv::Path do

  let(:full_path) {
      {
        :path      => 'foo/bar/fubb.txt',
        :directory => 'foo/bar',
        :file_name => 'fubb.txt',
        :extension => '.txt',
        :stem      => 'fubb',
      }
  }

  let(:bare_file_name) {
      {
        :path      => 'fubb',
        :directory => '.',
        :file_name => 'fubb',
        :extension => '',
        :stem      => 'fubb',
      }
  }

  let(:extra_chars) {
      {
        :path      => 'foo//bar//fubb..txt',
        :directory => 'foo//bar',
        :file_name => 'fubb..txt',
        :extension => '.txt',
        :stem      => 'fubb.',
      }
  }

  let(:empty_path) {
      {
        :path      => '',
        :directory => '.',
        :file_name => '',
        :extension => '',
        :stem      => '',
      }
  }

  def check_attributes(h)
    bp = Bmv::Path.new(h[:path])
    h.each { |k, v| expect(bp.send(k).to_s).to eq(v) }
  end

  it 'valid paths' do
    check_attributes(full_path)
    check_attributes(bare_file_name)
    check_attributes(extra_chars)
    check_attributes(empty_path)
  end

  it 'nil path' do
    expect { Bmv::Path.new(nil) }.to raise_error TypeError
  end

end

