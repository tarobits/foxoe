# Changelog

Notable changes to FoxOE are recorded here using
[Keep a Changelog 1.1.0](https://keepachangelog.com/en/1.1.0/)
and [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
GitHub release tags use the `v` prefix, for example `v1.0.0`.

## [Unreleased]

## [0.1.0-pre5] - 2026-11-23

**Test version / proof of concept.** These changes still require validation on
the physical Raspberry Pi, Stream Deck, and live Chromium setup.

### Added

- Icon, text, and background colors for Stream Deck buttons and app launcher keys, configurable through dashboard settings and the application API, with a preview and reset to defaults.
- Optional password-protected HTTPS dashboard administration from another computer, with self-signed certificate setup that runs as the kiosk user without sudo.
- Automatic extension updates alongside FoxOE, including restoration of extension files if deployment fails.

### Changed

- Managed installations load the Chromium extension from a stable `extension/` directory instead of `current/extension`.

Existing installations require a one-time extension migration after updating:
run `bash ~/.local/share/foxoe/current/update.sh --sync-extension`, remove the old
extension in Chromium, load `~/.local/share/foxoe/extension/` unpacked, pair it
again, and reload the kiosk page once. See the
[deployment guide](docs/DEPLOYMENT.md#automatic-extension-updates).

## [0.1.0-pre4] - 2026-11-23

**Test version / proof of concept.** These changes still require validation on
the physical Raspberry Pi and Stream Deck setup.

### Added

- Text-only app launchers and Stream Deck buttons using `icon: null` or the dashboard's No icon option.
- Per-key text sizes from 8 to 32 pixels, configurable through application registration, live button updates, and launcher settings. The default remains 14 pixels.
- The complete Heroicons outline collection with searchable selection in dashboard settings; existing icon names remain supported.

### Changed

- Stream Deck labels wrap and truncate with an ellipsis to fit the selected text size; larger text reduces the space available for its icon.

## [0.1.0-pre3] - 2026-11-23

**Test version / proof of concept.** Target hardware and live Chromium integration
still require validation for these changes.

### Added

- Fox illustration for the dashboard and browser extension, with built-in action icons and a house icon on Stream Deck keys.

### Fixed

- Correct generated systemd paths and avoid stopping a nonexistent service during fresh installation.
- Detect port conflicts before a fresh installation builds, and provide readable service logs for new installations with clearer health-check errors.
- Retry the browser's initial page connection automatically without requiring a settings save, and prevent duplicate startup connections.

After updating, reload the unpacked FoxOE extension in Chromium to activate its
connection fixes and new icon. The service updater does not reload Chromium.

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

[Unreleased]: https://github.com/tarobits/foxoe/compare/v0.1.0-pre5...main
[0.1.0-pre5]: https://github.com/tarobits/foxoe/compare/v0.1.0-pre4...v0.1.0-pre5
[0.1.0-pre4]: https://github.com/tarobits/foxoe/compare/v0.1.0-pre3...v0.1.0-pre4
[0.1.0-pre3]: https://github.com/tarobits/foxoe/compare/v0.1.0-pre2...v0.1.0-pre3
[0.1.0-pre2]: https://github.com/tarobits/foxoe/compare/v0.1.0-pre1...v0.1.0-pre2
[0.1.0-pre1]: https://github.com/tarobits/foxoe/releases/tag/v0.1.0-pre1
