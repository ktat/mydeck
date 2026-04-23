# OpenAction / Elgato-compatible Plugins (experimental)

MyDeck can run unmodified Elgato Stream Deck plugins (or OpenAction plugins)
via the `AppOpenActionBridge` background app. This is an **alpha** feature and
supports only a subset of the SDK (key-type actions, `setImage`, `setTitle`).
Dials, Property Inspector HTML, `switchToProfile`, and `setSettings` persistence
are not yet implemented.

## Prerequisites

- Install Node.js 20 or 24 (required by most Elgato plugins).
- Install MyDeck with the `openaction` extra:

```
pip install '.[openaction]'
```

## Installing a plugin

Place the plugin's `.sdPlugin/` folder under `~/.config/mydeck/plugins/`:

```
~/.config/mydeck/plugins/
  com.example.soundboard.sdPlugin/
    manifest.json
    bin/plugin.js
    ...
```

## Enabling the bridge

Add the bridge to your `apps:` in the per-device YAML:

```yaml
apps:
  - app: OpenActionBridge
    option:
      plugins_dir: ~/.config/mydeck/plugins
```

## Assigning an action to a key

Use the new `action:` key type in `page_config`:

```yaml
page_config:
  "@HOME":
    keys:
      0:
        action: "com.example.soundboard.play"
        settings:
          file: /path/to/ding.wav
          volume: 0.8
```

The plugin draws the button image and title dynamically via `setImage` /
`setTitle`.

## Limitations in MVP

- Property Inspector HTML is not rendered; configure via the YAML `settings:`
  field by hand.
- `setSettings` from the plugin is not persisted back to YAML.
- Only one deck is supported per bridge instance.
- Multi-state (`setState`) is not yet wired through to re-render.
- Dial/touchscreen actions are out of scope.
