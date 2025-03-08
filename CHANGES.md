## 1.0.0

- Initial release.

## 2.0.0

- Abandoned the v1 approach to problem control and instead adopted a policy of
  eager renaming with informed consent (see --details policy). Problem names
  and classifications were reorganzied, simplified, and expanded to cover other
  situations. The old problem-control mechanisms requiring users to specify in
  advance which types of problems were acceptable in renaming scenarios were
  dropped (--skip, --clobber, and --create). Under v2 users only need to use
  the new problem-related options (--skip and --strict) if they want to apply
  additional rigor or strictness beyond the default behavior.

- Enhanced listing behavior (and added --list) to provide better support for
  the new model of eager renaming with informed consent.

- Expanded detailed help (see --details).

- Policy changes and clarifications. (1) Orignal paths must be directories or
  regular files. (2) The mvs code will create missing parents but it will not
  execute renamings that require modifying the parent portions of existing
  paths (see --details caveats).

- Added support for case-change-only renamings.

- Added user preferences (and --disable).

- Added the --edit option (and --editor).

- Different and additional variables are made available to user-supplied
  renaming and filtering code.

- Bug fix involving renamings on Windows when replacing/clobbering an existing
  path.

