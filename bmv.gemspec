# lib = File.expand_path('../lib', __FILE__)
# $LOAD_PATH.unshift(lib) unless $LOAD_PATH.include?(lib)
# require 'bmv/version'

Gem::Specification.new do |spec|

  spec.name          = 'bmv'
  spec.version       = '0.0.1'    # Bmv::VERSION
  spec.authors       = ['Monty Hindman']
  spec.email         = ['montyhindman@gmail.com']
  spec.summary       = ''
  spec.description   = ''
  spec.homepage      = 'https://github.com/hindman/bmv'
  spec.license       = 'MIT'

  spec.files         = `git ls-files -z`.split("\x0")
  spec.executables   = spec.files.grep(%r{^bin/}) { |f| File.basename(f) }
  spec.test_files    = spec.files.grep(%r{^(test|spec|features)/})
  spec.require_paths = ['lib']

  spec.add_development_dependency 'bundler', '~> 1.6'
  spec.add_development_dependency 'rake'

end

