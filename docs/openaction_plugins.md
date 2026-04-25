# OpenAction / Elgato-compatible Plugins

MyDeck can run unmodified Elgato Stream Deck plugins (and OpenAction plugins)
via the `AppOpenActionBridge` background app. Most everyday plugin types work
on Linux without changes; configuration is done from the Web UI rather than
the official Elgato app.

## What's supported

- **Plugin runtimes**
  - Native binaries (Linux ELF executables)
  - Python (`*.py`)
  - Node.js (`*.js`, `.mjs`, `.cjs`)
  - HTML / browser-based plugins (`CodePath: index.html`) via headless
    Chromium (Playwright with system `google-chrome` / `chromium` fallback)
- **Protocol**
  - `setImage` (PNG / JPEG / SVG via cairosvg)
  - `setTitle` (composited as a text overlay on top of the image, matching
    Elgato semantics)
  - `setSettings` / `getSettings` (persisted to
    `~/.config/mydeck/openaction-settings.json`)
  - Property Inspector (PI) — loaded in an iframe inside the Web UI key
    config dialog and connected to the bridge via the same WebSocket the
    plugin uses
  - `sendToPlugin` / `sendToPropertyInspector` (PI ↔ plugin)
  - `logMessage`
- **Multi-deck** — every connected deck appears in the plugin's `-info`
  payload; events are routed by serial number
- **Hot reload** — uploading or uninstalling a plugin from the Web UI
  spawns / terminates its process without restarting `mydeck`

## What's NOT supported

- Dials and touchscreen actions
- Multi-state actions (`setState` is not yet re-rendered)
- Plugins that ship only Mac / Windows native binaries (no Linux code path)
- Audio output from headless Chromium (HTML plugins like Tomato Timer's
  bell sound are silent)

## Prerequisites

Install MyDeck with the OpenAction extra. To enable HTML plugins as well,
add the `html-plugins` extra (depends on Playwright):

```sh
# Native / Node / Python plugins only
uv tool install --with 'websockets>=12' mydeck

# Including HTML / browser-based plugins
uv tool install --with 'websockets>=12' --with 'playwright>=1.40' mydeck
```

If Playwright cannot install its bundled Chromium on your distro (e.g.
Ubuntu 26.04 is not in its supported list yet), the bridge automatically
falls back to a system `google-chrome` or `chromium` if either is on PATH.

## Enabling the bridge

Add the bridge to one device's `apps:` in the per-device YAML. You only
need to do this on a single deck — the bridge handles all connected decks
in the same session.

```yaml
apps:
  - app: OpenActionBridge
    option: {}
    # optional overrides:
    #   plugins_dir: ~/.config/mydeck/plugins
    #   settings_path: ~/.config/mydeck/openaction-settings.json
    #   port: 0   # 0 = pick a free port
```

## Installing a plugin

### From the Web UI (recommended)

1. Open `http://127.0.0.1:3000/#plugins` (or **Plugins → Manage Plugins**
   in the header).
2. Click the file picker and choose a `.streamDeckPlugin` archive.
3. The plugin is extracted under `~/.config/mydeck/plugins/`, registered,
   and **spawned immediately** — no daemon restart needed.
4. Encrypted Marketplace manifests (`ELGATO`-prefixed binary blobs) are
   detected automatically. The bridge scans the bundled JS for action
   UUIDs and writes a synthesized `manifest.json` so the plugin is usable
   anyway. The original encrypted blob is kept as
   `manifest.json.elgato-encrypted` for reference.

### Manually

Drop the plugin's `.sdPlugin/` folder under `~/.config/mydeck/plugins/`,
then restart `mydeck` (or use the upload flow above to trigger a hot
reload).

## Assigning an action to a key

Right-click a key in the Web UI, choose **Plugin Action** in the type
dropdown, then pick the plugin and action you want. If the action ships
a Property Inspector, an iframe loads it in the dialog; changes are
saved live via the standard Elgato `setSettings` flow. Press **SAVE** to
persist the binding (`action: <uuid>`) to the per-deck YAML.

You can also set this by hand:

```yaml
page_config:
  "@HOME":
    keys:
      0:
        action: "com.example.soundboard.play"
        settings:           # initial settings (optional)
          file: /path/to/ding.wav
          volume: 0.8
```

Stored runtime settings (whatever the plugin or PI calls `setSettings`
with) merge over these YAML defaults — the runtime store wins.

## Uninstalling

From the Web UI's **Manage Plugins** page, click **Uninstall** next to a
plugin. Its process is stopped and its directory is removed. Any keys
still bound to one of its action UUIDs will simply remain blank until
you reconfigure them.

## Troubleshooting

- **Key shows nothing on a second deck.** The bridge waits a few seconds
  on startup for additional decks to attach before reading the device
  list. If your second deck connects later, restart `mydeck` so it
  appears in plugins' `-info` payload.
- **Plugin extracted but does not show up in the list.** The Web UI
  surfaces this as an explicit error and rolls back the extraction —
  usually the manifest is missing a Linux `CodePath` (the plugin is
  Mac/Windows only).
- **Property Inspector is empty / blank in the iframe.** Some PIs use
  CDN-hosted scripts (e.g. `sdpi-components.dev`) that need internet
  access; the iframe runs in your normal browser, so it inherits the
  browser's connectivity.
- **HTML plugin fails to register.** The bridge waits up to 5 seconds
  for `connectElgatoStreamDeckSocket` to appear in the page. Slow
  startup or a JS error in the plugin can exceed this; check
  `pageerror` warnings in the daemon log.

## How it works

```
[Stream Deck device] ─USB HID─> [MyDeck]
                                   │ key_change_callback
                                   ▼
                           [AppOpenActionBridge]
                                   │ WebSocket  (port chosen at startup)
                                   ▼
        ┌──────────────────────────┼──────────────────────────┐
        ▼                          ▼                          ▼
 [native / Node / Python   [HTML plugin tab in    [Property Inspector iframe
  plugin process]           shared headless        in the Web UI, served from
                            Chromium]              /pi/<uuid>.sdPlugin/...]
```

The bridge multiplexes everything over one WebSocket server. PIs register
with `registerPropertyInspector` (vs. `registerPlugin`) and are routed to
their plugin via the per-key context token.
