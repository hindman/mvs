require 'spec_helper'

describe Bmv::Renaming do

  let(:br) {
    Bmv::Renaming.new('foo', 'bar')
  }

  context 'path setting' do

    it 'nil in constructor' do
      r = Bmv::Renaming.new(nil, nil)
      expect(r.old_path).to be nil
      expect(r.new_path).to be nil
    end

    it 'set with nil' do
      r = Bmv::Renaming.new(nil, nil)
      r.old_path = nil
      r.new_path = nil
      expect(r.old_path).to be nil
      expect(r.new_path).to be nil
    end

    it 'set with non-nil' do
      r = Bmv::Renaming.new(nil, nil)
      r.old_path = 'foo'
      r.new_path = 'xxx'
      expect(r.old_path).to be_a Bmv::Path
      expect(r.new_path).to be_a Bmv::Path
    end

  end

  context 'convenience getters' do

    it 'can exercise all' do
      ks = %w(
        p  path
        d  dir
        f  file
        s  stem
        e  ext
      )
      ks.each { |k|
        expect(br.send(k)).to be_a String
      }
    end

    it 'expected values' do
      h = {
        :path => 'foo/bar/fubb.txt',
        :dir  => 'foo/bar',
        :file => 'fubb.txt',
        :ext  => '.txt',
        :stem => 'fubb',
      }
      r = Bmv::Renaming.new(h[:path], nil)
      h.each { |k, v|
        expect(r.send(k)).to eql(v)
      }
    end

  end

  context 'can exercise' do

    it '#to_h' do
      expect(br.to_h).to be_a Hash
      expect(br.to_h(true)).to be_a Hash
    end

    it '#to_s' do
      expect(br.to_s).to be_a String
    end

  end

end

