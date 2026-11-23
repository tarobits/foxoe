# FoxOE — Fox Operating Environment

A local kiosk dashboard for a Raspberry Pi 3B+ and 1024×600 touchscreen, with a
permanent application dock and an Elgato Stream Deck MK.2 that follows the active
browser application.

**v0.1.0-pre1 is a test version and proof of concept**, intended for experimentation
rather than production use. Target hardware and live Chromium integration still
need validation. Install this prerelease with `bash install.sh --channel beta`.

## What is implemented

- Configurable clock, text, value, and list widgets above the application dock.
- Dragging, resizing, keyboard positioning, and explicit grid coordinates.
- Live system load, Linux memory/temperature readings, and bounded JSON API polling.
- Chromium integration for one selected kiosk tab, same-tab navigation, and Home.
- App-defined Stream Deck layouts, named screens, temporary keypad layouts, and
  individual button updates.
- Automatic app registration with a setup credential, per-app update credentials,
  and PNG/JPEG/WebP button images.
- English and German interfaces, saved configuration, revision conflict detection,
  and an optional USB worker with reconnect handling.

The label printer application itself has not been modified. Configure its real
URL and queue endpoint, and integrate the SDK in its frontend to expose its actions.
The included FoxOE Demo exercises numeric input without printing anything.

## Run locally

Use Python 3.11 or newer and Node.js 22.18 or newer. Node is needed to build the
frontend, not to run the built kiosk service.

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[device,test]'
npm ci
npm run build
.venv/bin/python -m foxoe
```

Open **http://127.0.0.1:8765/** on the same machine. Use `--no-device` for a desktop
preview without USB discovery. Runtime state and credentials are created under
`data/`, which is ignored by Git. `--data-dir` selects another private directory.

The product is named FoxOE; this checkout's directory is still
`FoxStreamDeckManager` because an older sibling `FoxOE` project already exists.
That older project has not been changed.

## Install and update on Raspberry Pi OS

From a downloaded or cloned FoxOE source folder, run as the kiosk user:

```sh
bash install.sh
```

The installer selects the newest stable semantic version published in
[GitHub Releases](https://github.com/tarobits/foxoe/releases), builds it, and starts
a user service. It installs OS dependencies and USB access using `sudo`, and uses
a private Node.js installation if the available Node version is too old. It
requires Raspberry Pi OS/Debian with Python 3.11 or newer. An empty repository or
one without a published release cannot be installed yet.

Update the managed installation with:

```sh
bash ~/.local/share/foxoe/current/update.sh
bash ~/.local/share/foxoe/current/update.sh --channel beta
bash ~/.local/share/foxoe/current/update.sh --channel stable
```

The selected channel is remembered after a successful update, or immediately if
the installed version is already current. `beta` includes prereleases and final
releases; `stable` excludes prereleases. Returning to stable waits for a release
that catches up with the installed version; it does not downgrade your data.
Updates build separately, preserve settings and credentials, and restore the
previous release and data snapshot if activation fails.

See [deployment options and recovery](docs/DEPLOYMENT.md) and the
[changelog](CHANGELOG.md). No release is published by these scripts.

## Raspberry Pi USB and kiosk setup

For manual installation, install `libhidapi-libusb0` and `fonts-dejavu-core` through the Pi's package manager.
The former provides USB access; the latter provides readable key labels. Run FoxOE
as an ordinary account, with USB access through the supplied
[udev example](deploy/60-foxoe-streamdeck.rules). Assign only the kiosk service
account to that rule's `plugdev` group; reload udev rules and reconnect the device.

The rule targets known MK.2 USB product IDs. Check `lsusb` if a different hardware
revision is not detected. FoxOE currently selects the first connected visual
15-key deck; multi-device selection is not implemented.

Build on another machine and copy `dist/` with the checkout if building on the Pi
is too slow. The [user service example](deploy/foxoe.service) assumes the checkout
is at `~/FoxOE`; adjust its two paths to the actual installation. The installer
instead generates the unit for its managed installation directory. Reboot once
after using the installer and reconnect the deck to apply USB group membership.

In a **dedicated Chromium profile**, load `~/.local/share/foxoe/current/extension/`
(or `extension/` for a manual installation) as an unpacked extension
through `chrome://extensions`. The extension requests HTTP/HTTPS host access so
newly registered app origins work without another permission dialog. It injects
its bridge only into the selected kiosk tab and validates top-frame/document
identity before accepting app actions.

1. In FoxOE Settings → System, reveal the **browser connection token**.
2. Paste it into the extension's options and save.
3. Open the FoxOE dashboard and click the extension's toolbar icon to select that
   tab as the kiosk. Do this before entering fullscreen kiosk mode.
4. Start Chromium in kiosk mode at `http://127.0.0.1:8765/` using that profile.

The toolbar selection persists while the tab exists. After a browser restart,
the extension selects the dashboard tab if it finds exactly one; otherwise use
the toolbar to select the intended tab. Home remains reserved as key 15. Changing
tabs, navigating, or losing browser focus releases the active app's controls.

## Customize the dashboard

Use **Edit dashboard** to add, move, resize, and configure widgets. Changes become
persistent only when saved; Cancel discards the draft. The grid has 12 columns,
24 rows, and rejects overlaps. On narrow screens widgets stack; position and size
remain editable through fields.

Add JSON endpoints under Settings → Data sources. Widget paths support ordinary
properties and numeric array indices, such as `queue.items` or `jobs[0].name`.
They do not execute JavaScript or JSONPath expressions. For list widgets, the
item path selects a scalar field from each item. Up to 100 entries are displayed,
with an indicator for additional entries. JSON responses are capped at 256 KiB;
arrays are capped at 200 retained entries.

The built-in `system` source measures the machine running FoxOE. `load1` is the
one-minute load average, not CPU utilization percentage. Linux-only measurements
show **No data** on hosts that do not expose them. External API failures retain
the last successful value and visibly mark it as stale.

For authenticated sources, set an environment variable beginning with
`FOXOE_SECRET_` in the service environment and enter only its name in Settings.
FoxOE sends its value as a Bearer token. Redirects are not followed, operations
have an eight-second overall deadline, and credentials are not sent to the browser.

## Register apps from another machine

Enable the separate HTTPS listener using a certificate and private key valid for
the Pi's hostname:

```sh
.venv/bin/python -m foxoe \
  --registration-cert /path/to/fullchain.pem \
  --registration-key /path/to/private-key.pem
```

The registration API listens on port **8766** by default; its host and port can
be changed with `--registration-host` and `--registration-port`. It exposes only
`POST /v1/apps` and `PUT /v1/apps/{id}`. The kiosk UI, local settings, credentials,
and browser bridge remain on **127.0.0.1:8765**. Do not proxy that local listener
onto the network: local settings deliberately rely on the appliance boundary,
not an administrator login.

Reveal the separate **setup credential** under Settings → System → App registration
and give it to trusted application servers. Keep it out of browser JavaScript.
Use certificate verification; for a private CA, configure that CA in the client.
See [the API contract](docs/API.md) and [registration example](examples/register.py).

## Development and verification

```sh
npm run dev       # frontend development server; keep the Python service running
npm run build     # TypeScript check and production build
npm test          # SDK, routing, data paths, grid boundaries, locale tests
.venv/bin/python -m pytest -q
```

Use the built service at port 8765 for browser-extension integration. The Vite
development URL is not the extension's Home origin.

Automated tests exercise validation, conflicts, stale input, cancellation,
recovery, credential scoping, image limits, and the USB adapter through a fake
device. Local Safari checks cover dashboard layouts at 1024×600 and 390×844,
settings save, widget collision feedback, dialog closing, and touch keypad input.
Physical MK.2 operation, Pi performance, and a live Chromium extension session
still require hardware/browser integration testing.

## License

FoxOE is licensed under the [PolyForm Noncommercial License 1.0.0](LICENSE).
The official terms are at
[polyformproject.org](https://polyformproject.org/licenses/noncommercial/1.0.0).
Third-party dependencies retain their own licenses; the frontend build preserves
bundled dependency license comments and includes [third-party notices](public/THIRD_PARTY_NOTICES.txt).
The supplied `DESIGN.md` is the user's
reference design, with FoxOE-specific adaptations documented separately.
