# Installing and updating FoxOE

The scripts target Raspberry Pi OS/Debian Linux with systemd and Python 3.11+.
Run them as the ordinary kiosk user in a login session with a working user service
manager. Do not run the scripts themselves with `sudo`. Installation requests
privileges only for OS packages and USB access; user lingering enables the service
at boot. Chromium profile setup and extension pairing remain manual.

## Install

Download/extract the project source or clone `https://github.com/tarobits/foxoe.git`,
then run:

```sh
bash install.sh
```

Development uses `main`, but installation never deploys its untagged commits.
The installer queries published GitHub releases, selects the highest eligible
semantic version, fetches its exact Git tag, and builds it. The initial channel
is `stable`. Draft releases, unpublished tags, and non-SemVer tags are excluded.
If no eligible release exists, installation stops before OS setup.

Options:

```sh
bash install.sh --version v1.0.0
bash install.sh --channel beta --version v1.1.0-beta.1
bash install.sh --directory "$HOME/foxoe-runtime"
bash install.sh --skip-system-deps
```

`--skip-system-deps` skips apt packages, USB rules/group membership, and lingering.
Use it only when those prerequisites are already configured. The installer will
still prepare Python dependencies and the frontend toolchain. Supported Node.js
and npm are reused; otherwise a pinned official Node.js 22 archive for ARMv7,
ARM64, or x64 is downloaded over HTTPS and verified against its SHA-256 manifest.
No Node installation is made system-wide. Builds require internet access to
GitHub, npm, PyPI, and potentially nodejs.org and the OS package repositories.

The managed installation defaults to `~/.local/share/foxoe`:

| Path | Contents |
| --- | --- |
| `current` | Symlink to the active release |
| `releases/` | Separate source, Python environment, and frontend build per deployment |
| `data/` | Persistent dashboard configuration, images, and credentials |
| `installation.json` | Repository, installed version/commit, and update channel |
| `backups/` | Data snapshots made while the service is stopped |
| `service.env` | Optional operator-managed environment variables |
| `pending.json` | Recovery journal during an activation |

An existing `foxoe.service` is never overwritten by a fresh install. The scripts
do not import a developer checkout's `data/` automatically. Keep manual and managed
installations separate; only one service can occupy port 8765.

The generated unit is `~/.config/systemd/user/foxoe.service`. It runs without root,
uses a private umask, and restarts on failure. Use `systemctl --user status foxoe`
and `journalctl --user -u foxoe` for service diagnostics. After the initial USB
setup, reboot once and reconnect the Stream Deck so group membership is applied.

## Updates and channels

```sh
bash ~/.local/share/foxoe/current/update.sh
bash ~/.local/share/foxoe/current/update.sh --channel beta
bash ~/.local/share/foxoe/current/update.sh --channel stable
```

`stable` accepts published final releases. `beta` accepts published prereleases
and finals, selecting by SemVer precedence: `v1.1.0-beta.10` follows
`v1.1.0-beta.2`, and `v1.1.0` follows both. The beta channel can include alpha or
release-candidate tags too. GitHub's prerelease flag and the tag are both checked
when filtering stable releases.

The selected channel is saved with a successful deployment. If already current,
only channel metadata changes. Explicitly switching back to stable while ahead
of it saves the channel and keeps the current version until stable catches up.
If an attempted deployment fails, the previous version and channel are restored.
An explicitly requested older `--version` is rejected. Build metadata does not
change SemVer precedence.

Use `--directory` on every invocation for a nondefault runtime directory.
`--version vX.Y.Z` selects a specific published release within the selected channel.
The updater uses the saved repository and never pulls `main`. Updates are run on
demand; the scripts do not install a scheduled updater.

The running release remains available during dependency installation and build.
Only activation stops the service: data is snapshotted, `current` is switched,
and the new process and dashboard are checked. The probe verifies systemd's PID
and release identity so another process on port 8765 cannot pass the health check.
Failure restores the previous code and complete data snapshot, including
credentials. Operations accepted by the new process during its short probation
period are discarded if it rolls back.

Chromium loads its unpacked extension from `current/extension`. Reload the
extension or restart the dedicated browser when extension files change; the
service updater does not control Chromium itself.

## Recovery and retained files

Interrupted activations are recovered before the next install/update. To recover
without fetching another release:

```sh
bash ~/.local/share/foxoe/current/update.sh --recover
```

If `current` is unavailable after a failed first install, run the same command
from the original source folder instead. The activation journal stays present
when recovery itself fails, so a later retry can restore the saved data. Correct
the underlying disk/service issue first and inspect the service journal.

Old releases, data snapshots, and `failed-data-*` directories are retained for
inspection. They can contain private credentials and are stored under the private
runtime directory. No automatic retention deletion is performed; monitor disk
space and remove only snapshots/releases you no longer need. Never delete the
active release or files referenced by `pending.json`.

## Service customization

Updates preserve the unit, drop-ins, and `service.env`. Put data-source secrets in
`service.env` with mode `0600`, using the `FOXOE_SECRET_…` names from the application
settings. Do not commit that file. Use a systemd user-unit override for the
optional registration certificate and key arguments; retain `--data-dir` pointing
at the managed `data/` directory. The installer does not generate TLS certificates
or expose the local settings listener to the network.

## Preparing a release

Maintain [CHANGELOG.md](../CHANGELOG.md) using Keep a Changelog 1.1.0. Gather entries
from actual changes since the preceding release, under Added, Changed, Fixed,
Removed, and Security as applicable. Omit empty categories. Keep unreleased work
under `## [Unreleased]`.

For a release such as `v1.0.0`:

1. Set `pyproject.toml`, `package.json`, and the package lock version to `1.0.0`.
2. Move the applicable changelog entries into `## [1.0.0] - YYYY-MM-DD` using the
   actual release date; add a comparison link against the previous release.
3. Validate the build and tests. Tag the reviewed commit `v1.0.0` on `main` and
   publish a GitHub release for that tag with its changelog section as the notes.

For `v1.1.0-beta.1`, use `1.1.0-beta.1` in npm, `1.1.0b1` (or base `1.1.0`) in
Python, and `## [1.1.0-beta.1] - YYYY-MM-DD` in the changelog. Mark the GitHub release
as a prerelease. The installer checks package versions and the dated changelog
entry before installing dependencies. Publishing remains a separate explicit
maintainer action; these scripts never commit, tag, push, or publish.

Only document exceptional manual upgrade requirements in a release's notes,
such as a breaking configuration change or restricted rollback. Ordinary service
restarts, database snapshots, and dependency updates are handled by deployment.

References: [GitHub Releases API](https://docs.github.com/en/rest/releases/releases),
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and
[systemd user lingering](https://www.freedesktop.org/software/systemd/man/latest/loginctl.html).
