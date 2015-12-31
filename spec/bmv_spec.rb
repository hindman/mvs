require 'spec_helper'

describe Bmv do
  it 'has a version number' do
    expect(Bmv::VERSION).not_to be nil
  end

  it 'does something useful' do
    expect(Bmv.twelve).to eq(12)
  end
end

