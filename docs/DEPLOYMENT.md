# Installing and updating FoxOE

The scripts target Raspberry Pi OS/Debian Linux with systemd and Python 3.11+.
Run installation and updates as the ordinary kiosk user in a login session with
a working user service manager. This account does not need sudo access. A separate
administrator setup prepares OS packages, USB access and user lingering for boot
startup. Chromium profile setup and extension pairing remain manual.

## Install

Download/extract the project source or clone `https://github.com/tarobits/foxoe.git`,
then have an administrator run the following, replacing `kiosk` with the existing
account that will run FoxOE:

```sh
sudo bash setup-system.sh --user kiosk
```

An administrator already logged in as root uses `bash setup-system.sh --user kiosk`
without `sudo`. Setup does not create the account, grant it sudo access, build
application dependencies, or write application files into its home directory.
Reboot once and reconnect the deck, then log in directly as that kiosk user and run:

```sh
bash install.sh
```

Development uses `main`, but installation never deploys its untagged commits.
The installer queries published GitHub releases, selects the highest eligible
semantic version, fetches its exact Git tag, and builds it. The initial channel
is `stable`. Draft releases, unpublished tags, and non-SemVer tags are excluded.
If no eligible release exists, installation stops without installing an application.

Options:

```sh
bash install.sh --version v1.0.0
bash install.sh --channel beta --version v1.1.0-beta.1
bash install.sh --directory "$HOME/foxoe-runtime"
```

System setup is always separate. The old `--skip-system-deps` option remains a
compatibility no-op. The installer prepares Python dependencies and the frontend
toolchain entirely as the kiosk user. Supported Node.js
and npm are reused; otherwise a pinned official Node.js 22 archive for ARMv7,
ARM64, or x64 is downloaded over HTTPS and verified against its SHA-256 manifest.
No Node installation is made system-wide. Builds require internet access to
GitHub, npm, PyPI, and potentially nodejs.org and the OS package repositories.

The managed installation defaults to `~/.local/share/foxoe`:

| Path | Contents |
| --- | --- |
| `current` | Symlink to the active release |
| `extension/` | Stable unpacked extension directory, updated and restored with the service |
| `releases/` | Separate source, Python environment, and frontend build per deployment |
| `data/` | Persistent dashboard configuration, images, and credentials |
| `installation.json` | Repository, installed version/commit, and update channel |
| `backups/` | Data snapshots made while the service is stopped |
| `logs/service.log` | Service output retained across failed fresh installations |
| `service.env` | Optional operator-managed environment variables |
| `pending.json` | Recovery journal during an activation |

An existing `foxoe.service` is never overwritten by a fresh install. The scripts
do not import a developer checkout's `data/` automatically. Keep manual and managed
installations separate; only one service can occupy port 8765.

The generated unit is `~/.config/systemd/user/foxoe.service`. It runs without root,
uses a private umask, and restarts on failure. Newly generated units write service
output to `logs/service.log`, readable by the kiosk account without journal-group
membership. Use `systemctl --user status foxoe` for systemd status. Existing units
that still use journald may require an administrator to read their logs. After the initial USB
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

Chromium loads its unpacked extension from the stable runtime `extension/`
directory. Successful updates publish the extension files alongside the service.
The paired extension checks their build fingerprint and reloads itself; failed
deployments restore the previous extension files as well. Chromium itself is
not restarted, and application pages are not reloaded.

## Automatic extension updates

Existing installations that loaded `current/extension` need a one-time change
after installing the release that introduces automatic extension updates:

```sh
bash ~/.local/share/foxoe/current/update.sh --sync-extension
```

In `chrome://extensions`, remove the old FoxOE entry, load
`~/.local/share/foxoe/extension/` unpacked, and pair it with the local dashboard
again. Reload the kiosk page once to retire the old content script. The stable
directory avoids Chromium retaining a path to an older release. Future managed
updates reload the extension automatically after activation succeeds. Keep
loading that directory, not a version-specific release folder.

The extension checks through its authenticated local connection. It reloads
only when its own on-disk build matches the service's completed deployment,
and records each attempt to prevent reload loops. The selected tab is restored
only across an extension update when its ID and URL still match. Ordinary
browser restarts retain the existing dashboard-tab selection behavior.
Manual source installations still require a manual extension reload.

## Network administration

Run this once as the kiosk user (SSH is fine; no sudo is needed):

```sh
~/.local/share/foxoe/current/.venv/bin/python -m foxoe.admin_setup --hostname kiosk.local
systemctl --user restart foxoe
```

Replace `kiosk.local` with the Pi's hostname or LAN IP. The command prompts for
a separate administrator password of at least 12 characters and generates a
random private key and self-signed certificate. Open `https://kiosk.local:8767/`
from your other computer, accept the expected certificate warning for your Pi,
and sign in. If a firewall is enabled, allow TCP 8767 from your LAN. Use `--port`
to choose a different port, or `--data-dir` for a nondefault data directory.

The network listener is opt-in. The local kiosk remains at
`http://127.0.0.1:8765/` without a login. Remote administration can edit the
dashboard, apps, widgets, data sources, and key appearance; it does not expose
the browser bridge, connection tokens, or app registration credentials. Launcher
tiles are previews in the remote page and do not navigate the Pi's browser.

Sessions expire after eight hours, can be signed out, and are invalidated when
the service restarts. Passwords are stored as salted PBKDF2-HMAC-SHA256 hashes
with 600,000 iterations, following the [OWASP work-factor guidance](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html#pbkdf2).
Login attempts are rate-limited, and writes require a matching browser origin.

Run the same setup command to change or reset the password, then restart the
user service. The certificate stays the same across password changes and updates.
It expires after 825 days; to replace it, stop the service, move the two PEM files
out of `data/admin/`, rerun setup, and start the service. Browsers will show a new
certificate warning. The configuration, password hash, and TLS files live in
`data/admin/` and are included in the updater's data backups and rollback.

To disable remote access:

```sh
~/.local/share/foxoe/current/.venv/bin/python -m foxoe.admin_setup --disable
systemctl --user restart foxoe
```

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

Fresh installation checks that `127.0.0.1:8765` is free before downloading or
building. If it is occupied, identify its owner with `ss -ltnp 'sport = :8765'`
(an administrator may need to run this with `sudo` to see another user's process).
FoxOE never stops an unrelated listener automatically. Stop or reconfigure that
application before retrying installation.

If startup fails, read `logs/service.log` from the runtime directory. Health-check
errors include their last observed failure category. Logs survive rollback and
are not automatically rotated; monitor their size. Systemd errors before the
application starts may still require an administrator to inspect the journal.

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

The `0.1.0` series uses `v0.1.0-preview.10` after `v0.1.0-pre9`, followed by
`v0.1.0-preview.11`, and so on. Keep the counter as a separate numeric identifier:
SemVer sorts `pre10` before `pre9`, whereas `preview.10` follows `pre9` and future
`preview.N` tags sort numerically.

Only document exceptional manual upgrade requirements in a release's notes,
such as a breaking configuration change or restricted rollback. Ordinary service
restarts, database snapshots, and dependency updates are handled by deployment.

References: [GitHub Releases API](https://docs.github.com/en/rest/releases/releases),
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and
[systemd user lingering](https://www.freedesktop.org/software/systemd/man/latest/loginctl.html).
