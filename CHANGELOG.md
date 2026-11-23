# Changelog

Notable changes to FoxOE are recorded here using
[Keep a Changelog 1.1.0](https://keepachangelog.com/en/1.1.0/)
and [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
GitHub release tags use the `v` prefix, for example `v1.0.0`.

## [Unreleased]

## [0.1.0-pre2] - 2026-11-23

**Test version / proof of concept.** Target hardware and live Chromium integration
still require validation.

### Fixed

- Support kiosk accounts without sudo by separating administrator setup from user-owned installation and updates.

## [0.1.0-pre1] - 2026-11-23

**Test version / proof of concept.** This initial prerelease is intended for
experimentation and evaluation, not production use. Physical Stream Deck MK.2
operation, Raspberry Pi performance, the real Pi installer, and a live Chromium
extension session have not yet been validated on the target setup.

### Added

- Touchscreen dashboard with configurable information widgets and a permanent application dock.
- Live system information and widgets connected to JSON APIs.
- Stream Deck MK.2 controls that follow the active kiosk application, with Home navigation and temporary keypads.
- Application registration, predefined control screens, and custom button images.
- English and German interfaces.
- Raspberry Pi OS/Debian installation and updates from published GitHub releases, with remembered stable/beta channels, data preservation, and recovery after a failed activation.

[Unreleased]: https://github.com/tarobits/foxoe/compare/v0.1.0-pre2...main
[0.1.0-pre2]: https://github.com/tarobits/foxoe/compare/v0.1.0-pre1...v0.1.0-pre2
[0.1.0-pre1]: https://github.com/tarobits/foxoe/releases/tag/v0.1.0-pre1
