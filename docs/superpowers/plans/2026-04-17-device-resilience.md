# Device Resilience Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make mydeck survive USB disconnect, laptop sleep, and device removal without crashing, and auto-recover to the same page/apps when the device reconnects.

**Architecture:** Introduce `DeckGuard` (transparent proxy wrapping `real_deck`, catches `TransportError`/`OSError` and flips `VirtualDeck.connected=False`) and `DeviceSupervisor` (3-second polling thread that re-enumerates via `DeviceManager().enumerate()` and attaches new `real_deck` instances to matching `VirtualDeck`s by serial). A reserved `~DISCONNECTED` page (no keys/apps) is used during disconnect so existing `check_to_stop()` logic cleanly shuts down foreground apps; background apps keep running but their I/O becomes no-op via `DeckGuard`.

**Tech Stack:** Python 3, `python-elgato-streamdeck` (`StreamDeck` package), existing mydeck framework, `unittest`/`unittest.mock`.

**Spec:** `docs/superpowers/specs/2026-04-17-device-resilience-design.md`

---

## File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `src/mydeck/device_resilience.py` | Create | `DeckGuard` proxy + `DeviceSupervisor` polling thread |
| `src/mydeck/my_decks_manager.py` | Modify | Wrap `real_deck` with `DeckGuard`; add `connected`/`mark_disconnected`/`reattach` to `VirtualDeck`; register callback/supervisor dispatch |
| `src/mydeck/my_decks.py` | Modify | Add `_pre_disconnect_page`, `on_disconnect`/`on_reconnect` on `MyDeck`; start supervisor in `start_decks`; ensure `~DISCONNECTED` is accepted as a page name |
| `src/mydeck/my_decks_starter.py` | Modify | Allow starting when physical device isn't currently connected (known serial only) |
| `tests/test_device_resilience.py` | Create | Unit tests: DeckGuard proxying, disconnect detection, VirtualDeck state, MyDeck hooks, DeviceSupervisor |

---

## Task 1: DeckGuard — basic proxy (TDD)

**Files:**
- Create: `src/mydeck/device_resilience.py`
- Create: `tests/test_device_resilience.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_device_resilience.py`:

```python
import importlib.util
import os
import sys
import unittest
from unittest.mock import MagicMock

# Stub StreamDeck.Transport.Transport so we can import device_resilience
# without the native library installed in the test env.
transport_mod = MagicMock()
class _TransportError(Exception):
    pass
transport_mod.TransportError = _TransportError
sys.modules.setdefault('StreamDeck', MagicMock())
sys.modules.setdefault('StreamDeck.Transport', MagicMock())
sys.modules['StreamDeck.Transport.Transport'] = transport_mod

_module_path = os.path.join(
    os.path.dirname(__file__), '..', 'src', 'mydeck', 'device_resilience.py')
_spec = importlib.util.spec_from_file_location(
    'mydeck.device_resilience', _module_path)
_mod = importlib.util.module_from_spec(_spec)
sys.modules['mydeck.device_resilience'] = _mod
_spec.loader.exec_module(_mod)

DeckGuard = _mod.DeckGuard
TransportError = _TransportError


class FakeVirtualDeck:
    def __init__(self, serial='SN1'):
        self.connected = True
        self.serial = serial
        self.mark_disconnected_called = 0

    def get_serial_number(self):
        return self.serial

    def mark_disconnected(self):
        self.mark_disconnected_called += 1
        self.connected = False


class TestDeckGuardProxy(unittest.TestCase):
    def test_method_call_passes_through_when_connected(self):
        vd = FakeVirtualDeck()
        real = MagicMock()
        real.set_key_image.return_value = 'ok'
        guard = DeckGuard(vd)
        guard._set_real_deck(real)

        result = guard.set_key_image(0, 'img')

        self.assertEqual(result, 'ok')
        real.set_key_image.assert_called_once_with(0, 'img')


if __name__ == '__main__':
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /home/ktat/git/github/mystreamdeck && python3 -m pytest tests/test_device_resilience.py -v
```

Expected: FAIL (device_resilience.py does not exist).

- [ ] **Step 3: Create minimal implementation**

Create `src/mydeck/device_resilience.py`:

```python
"""Device resilience helpers: DeckGuard proxy and DeviceSupervisor thread.

DeckGuard transparently proxies calls to a real StreamDeck device, catching
TransportError/OSError so a USB disconnect or laptop sleep does not crash
mydeck. DeviceSupervisor periodically re-enumerates devices so mydeck can
reattach to a matching serial when the device comes back.
"""
import logging
from StreamDeck.Transport.Transport import TransportError

_GUARDED_METHODS = frozenset({
    'set_key_image', 'set_touchscreen_image', 'set_brightness',
    'reset', 'close', 'open',
    'set_key_callback', 'set_dial_callback', 'set_touchscreen_callback',
    'set_dial_callback_async', 'set_touchscreen_callback_async',
    'set_poll_frequency',
})


class DeckGuard:
    """Transparent proxy for a real StreamDeck.

    All attribute access is delegated to the wrapped real_deck. Method calls
    listed in _GUARDED_METHODS are wrapped so that TransportError/OSError
    triggers the owning VirtualDeck.mark_disconnected().
    """

    def __init__(self, virtual_deck):
        object.__setattr__(self, '_virtual_deck', virtual_deck)
        object.__setattr__(self, '_real_deck', None)

    def _set_real_deck(self, real_deck):
        object.__setattr__(self, '_real_deck', real_deck)

    def _get_real_deck(self):
        return object.__getattribute__(self, '_real_deck')

    def __getattr__(self, name):
        real_deck = object.__getattribute__(self, '_real_deck')
        vd = object.__getattribute__(self, '_virtual_deck')

        if real_deck is None:
            if name in _GUARDED_METHODS:
                return lambda *a, **kw: None
            raise AttributeError(name)

        attr = getattr(real_deck, name)

        if not getattr(vd, 'connected', True):
            if name in _GUARDED_METHODS and callable(attr):
                return lambda *a, **kw: None
            return attr

        if not callable(attr) or name not in _GUARDED_METHODS:
            return attr

        def wrapped(*args, **kwargs):
            try:
                return attr(*args, **kwargs)
            except (TransportError, OSError) as e:
                logging.info(
                    "Device %s disconnected during %s: %s",
                    vd.get_serial_number(), name, e)
                vd.mark_disconnected()
                return None

        return wrapped
```

- [ ] **Step 4: Run test to verify it passes**

```bash
python3 -m pytest tests/test_device_resilience.py::TestDeckGuardProxy::test_method_call_passes_through_when_connected -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/mydeck/device_resilience.py tests/test_device_resilience.py
git commit -m "feat(resilience): add DeckGuard proxy that forwards to real_deck"
```

---

## Task 2: DeckGuard — TransportError triggers disconnect

**Files:**
- Modify: `tests/test_device_resilience.py`

- [ ] **Step 1: Add failing tests**

Append to `tests/test_device_resilience.py` before `if __name__`:

```python
class TestDeckGuardDisconnect(unittest.TestCase):
    def test_transport_error_marks_disconnected(self):
        vd = FakeVirtualDeck()
        real = MagicMock()
        real.set_key_image.side_effect = TransportError("usb gone")
        guard = DeckGuard(vd)
        guard._set_real_deck(real)

        result = guard.set_key_image(0, 'img')

        self.assertIsNone(result)
        self.assertEqual(vd.mark_disconnected_called, 1)
        self.assertFalse(vd.connected)

    def test_oserror_marks_disconnected(self):
        vd = FakeVirtualDeck()
        real = MagicMock()
        real.set_brightness.side_effect = OSError("no device")
        guard = DeckGuard(vd)
        guard._set_real_deck(real)

        guard.set_brightness(30)

        self.assertEqual(vd.mark_disconnected_called, 1)

    def test_disconnected_write_is_noop(self):
        vd = FakeVirtualDeck()
        real = MagicMock()
        guard = DeckGuard(vd)
        guard._set_real_deck(real)
        vd.connected = False

        result = guard.set_key_image(0, 'img')

        self.assertIsNone(result)
        real.set_key_image.assert_not_called()

    def test_no_real_deck_write_is_noop(self):
        vd = FakeVirtualDeck()
        guard = DeckGuard(vd)
        # _set_real_deck never called

        result = guard.set_key_image(0, 'img')

        self.assertIsNone(result)

    def test_non_guarded_attribute_passes_through(self):
        vd = FakeVirtualDeck()
        real = MagicMock()
        real.KEY_COUNT = 15
        real.get_serial_number.return_value = 'SN1'
        guard = DeckGuard(vd)
        guard._set_real_deck(real)

        self.assertEqual(guard.KEY_COUNT, 15)
        self.assertEqual(guard.get_serial_number(), 'SN1')

    def test_other_exceptions_bubble(self):
        vd = FakeVirtualDeck()
        real = MagicMock()
        real.set_key_image.side_effect = ValueError("bad image")
        guard = DeckGuard(vd)
        guard._set_real_deck(real)

        with self.assertRaises(ValueError):
            guard.set_key_image(0, 'img')
        self.assertEqual(vd.mark_disconnected_called, 0)
```

- [ ] **Step 2: Run tests**

```bash
python3 -m pytest tests/test_device_resilience.py -v
```

Expected: all tests pass (DeckGuard already implements the behavior from Task 1 Step 3).

- [ ] **Step 3: Commit**

```bash
git add tests/test_device_resilience.py
git commit -m "test(resilience): cover DeckGuard disconnect semantics"
```

---

## Task 3: DeckGuard — context manager support

**Files:**
- Modify: `src/mydeck/device_resilience.py`
- Modify: `tests/test_device_resilience.py`

**Why:** `my_decks.py` does `with deck:` which needs `__enter__`/`__exit__` on the proxy. Python looks up dunder methods on the type, not via `__getattr__`.

- [ ] **Step 1: Add failing test**

Append before `if __name__`:

```python
class TestDeckGuardContextManager(unittest.TestCase):
    def test_context_manager_delegates(self):
        vd = FakeVirtualDeck()
        real = MagicMock()
        guard = DeckGuard(vd)
        guard._set_real_deck(real)

        with guard:
            pass

        real.__enter__.assert_called_once()
        real.__exit__.assert_called_once()

    def test_context_manager_noop_when_no_real_deck(self):
        vd = FakeVirtualDeck()
        guard = DeckGuard(vd)

        with guard:
            pass  # must not raise
```

- [ ] **Step 2: Run test — expect FAIL**

```bash
python3 -m pytest tests/test_device_resilience.py::TestDeckGuardContextManager -v
```

Expected: FAIL (AttributeError or TypeError — context manager protocol not implemented).

- [ ] **Step 3: Add __enter__/__exit__ to DeckGuard**

In `src/mydeck/device_resilience.py`, add methods inside `class DeckGuard` (after `__getattr__`):

```python
    def __enter__(self):
        real_deck = object.__getattribute__(self, '_real_deck')
        if real_deck is not None:
            try:
                real_deck.__enter__()
            except (TransportError, OSError):
                vd = object.__getattribute__(self, '_virtual_deck')
                vd.mark_disconnected()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        real_deck = object.__getattribute__(self, '_real_deck')
        if real_deck is not None:
            try:
                real_deck.__exit__(exc_type, exc_val, exc_tb)
            except (TransportError, OSError):
                vd = object.__getattribute__(self, '_virtual_deck')
                vd.mark_disconnected()
        return False
```

- [ ] **Step 4: Run tests**

```bash
python3 -m pytest tests/test_device_resilience.py -v
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add src/mydeck/device_resilience.py tests/test_device_resilience.py
git commit -m "feat(resilience): DeckGuard supports context manager protocol"
```

---

## Task 4: VirtualDeck — connected state + mark_disconnected/reattach

**Files:**
- Modify: `src/mydeck/my_decks_manager.py`

- [ ] **Step 1: Read current VirtualDeck constructor**

```bash
sed -n '231,310p' src/mydeck/my_decks_manager.py
```

- [ ] **Step 2: Modify `VirtualDeck.__init__` to wrap real_deck in DeckGuard**

In `src/mydeck/my_decks_manager.py`, at the top of the file near other imports, add:

```python
from .device_resilience import DeckGuard
```

Then in `VirtualDeck.__init__`, locate:

```python
    def __init__(self, opt: dict, input: 'DeckInput', output: 'DeckOutput'):
        """Pass Virutal Deck option, DeckInput instance and DeckOutput instance."""
        self.real_deck: StreamDeck = None
```

Replace that whole block up through `self.update_lock = threading.RLock()` with:

```python
    def __init__(self, opt: dict, input: 'DeckInput', output: 'DeckOutput'):
        """Pass Virutal Deck option, DeckInput instance and DeckOutput instance."""
        # connection state for physical devices; virtual-only decks stay True forever
        self.connected: bool = True
        # Callbacks set by the user are cached here so we can re-bind them to a
        # freshly-opened real_deck on reconnect.
        self._cached_key_callback = None
        self._cached_dial_callback = None
        self._cached_touchscreen_callback = None
        self._cached_brightness: int = 30
        self._cached_poll_frequency = None
        # disconnect/reconnect listener set by MyDecksManager
        self._lifecycle_listener = None
        # DeckGuard wraps the real device once one is attached.
        self._guard: DeckGuard = DeckGuard(self)
        # self.real_deck exposes the guard so existing call sites keep working.
        self.real_deck = self._guard
        self._has_real_deck: bool = False
        self.is_touch_interface: bool = False
        plus = StreamDeckPlus
        self.touchscreen_size: tuple[int, int] = (0, 0)
        self._exit: bool = False
        self.touchscreen_image = None
        self._dial_count: int = 0
        self._dial_states: Dict[int, int] = {}
        self.dial_callback: Callable = lambda deck, dial, event, value: None
        self.touchscreen_callback: Callable = lambda deck, event, args: None
        self.key_callback: Callable = lambda deck, key, flag: None

        key_count = opt.get('key_count')
        if type(key_count) is not int:
            raise (ExceptionVirtualDeckConstructor)
        self._key_count: int = key_count
        id: Optional[str] = opt.get('id')
        if type(id) is not str:
            raise (ExceptionVirtualDeckConstructor)
        self._id: str = id
        columns = opt.get('columns')
        if type(columns) is not int:
            raise (ExceptionVirtualDeckConstructor)
        self._columns: int = columns
        serial_number = opt.get('serial_number')
        if type(serial_number) is not str:
            raise (ExceptionVirtualDeckConstructor)
        dial_count: Optional[int] = opt.get('dial_count')
        if dial_count is not None and dial_count > 0:
            self._dial_count = dial_count
            for i in range(self._dial_count):
                self.set_dial_states(i, 0)

        has_touch: Optional[int] = opt.get('has_touchscreen')
        if has_touch is not None and has_touch is True:
            self.is_touch_interface = True
            size: Optional[tuple[int, int]] = opt.get("touchscreen_size")
            if size is not None and len(size) == 2:
                self.touchscreen_size = (size[0], size[1])
            else:
                self.touchscreen_size = (
                    plus.TOUCHSCREEN_PIXEL_WIDTH, plus.TOUCHSCREEN_PIXEL_HEIGHT
                )
        self.serial_number: str = serial_number
        self.firmware_version: str = 'dummy firmware'
        self.input: 'DeckInput' = input
        self.output: 'DeckOutput' = output
        self.current_key_status: dict = {}
        self.output.set_deck(self)
        self.input.set_deck(self)
        self.input.init()
        self.output.init()
        self.reset()
        self.update_lock = threading.RLock()
```

- [ ] **Step 3: Replace `has_real_deck` to use the flag**

Locate `def has_real_deck` and replace its body:

```python
    def has_real_deck(self) -> bool:
        return self._has_real_deck
```

- [ ] **Step 4: Add new methods `attach_real_deck`, `mark_disconnected`, `reattach`, `set_lifecycle_listener`**

Add these methods to `VirtualDeck` (e.g., right after `has_real_deck`):

```python
    def attach_real_deck(self, real_deck: StreamDeck) -> None:
        """Initial attach of a real_deck (called at startup for already-connected devices)."""
        self._guard._set_real_deck(real_deck)
        self._has_real_deck = True
        self.connected = True

    def set_lifecycle_listener(self, listener) -> None:
        """Register a callable invoked with (self, event) where event is
        'disconnected' or 'reconnected'."""
        self._lifecycle_listener = listener

    def mark_disconnected(self) -> None:
        """Called by DeckGuard when a TransportError/OSError is caught.

        Idempotent: multiple calls in quick succession from different threads
        result in a single listener notification.
        """
        with self.update_lock:
            if not self.connected:
                return
            self.connected = False
            listener = self._lifecycle_listener
        if listener is not None:
            try:
                listener(self, 'disconnected')
            except Exception as e:
                logging.error("lifecycle listener error on disconnect: %s", e)

    def reattach(self, real_deck: StreamDeck) -> None:
        """Swap in a freshly-opened real_deck (supervisor calls this on reconnect).

        Re-binds cached callbacks and restores brightness/poll frequency so the
        new physical device matches pre-disconnect state.
        """
        with self.update_lock:
            self._guard._set_real_deck(real_deck)
            self._has_real_deck = True
            self.connected = True
            if self._cached_key_callback is not None:
                try:
                    real_deck.set_key_callback(self._cached_key_callback)
                except Exception as e:
                    logging.error("reattach set_key_callback failed: %s", e)
            if self._cached_dial_callback is not None:
                try:
                    real_deck.set_dial_callback(self._cached_dial_callback)
                except Exception as e:
                    logging.error("reattach set_dial_callback failed: %s", e)
            if self._cached_touchscreen_callback is not None:
                try:
                    real_deck.set_touchscreen_callback(
                        self._cached_touchscreen_callback)
                except Exception as e:
                    logging.error(
                        "reattach set_touchscreen_callback failed: %s", e)
            try:
                real_deck.set_brightness(self._cached_brightness)
            except Exception as e:
                logging.error("reattach set_brightness failed: %s", e)
            if self._cached_poll_frequency is not None:
                try:
                    real_deck.set_poll_frequency(self._cached_poll_frequency)
                except Exception as e:
                    logging.error("reattach set_poll_frequency failed: %s", e)
            listener = self._lifecycle_listener
        if listener is not None:
            try:
                listener(self, 'reconnected')
            except Exception as e:
                logging.error("lifecycle listener error on reconnect: %s", e)
```

- [ ] **Step 5: Cache callbacks & brightness in existing setters**

Locate `set_key_callback`, `set_dial_callback`, `set_touchscreen_callback`, `set_brightness`, `set_poll_frequency` in `VirtualDeck`.

Replace `set_key_callback`:

```python
    def set_key_callback(self, func):
        """Set key callback"""
        self.key_callback = func
        self._cached_key_callback = func
        if self.has_real_deck():
            self.real_deck.set_key_callback(func)
```

Replace `set_dial_callback`:

```python
    def set_dial_callback(self, func) -> None:
        self.dial_callback = func
        self._cached_dial_callback = func
        if self.has_real_deck():
            self.real_deck.set_dial_callback(func)
```

Replace `set_touchscreen_callback`:

```python
    def set_touchscreen_callback(self, func) -> None:
        self.touchscreen_callback = func
        self._cached_touchscreen_callback = func
        if self.has_real_deck():
            self.real_deck.set_touchscreen_callback(func)
```

Replace `set_brightness`:

```python
    def set_brightness(self, d1):
        """Do nothing."""
        self._cached_brightness = d1
        if self.has_real_deck():
            return self.real_deck.set_brightness(d1)
```

Replace `set_poll_frequency`:

```python
    def set_poll_frequency(self, freq: int) -> None:
        self._cached_poll_frequency = freq
        if self.has_real_deck():
            self.real_deck.set_poll_frequency(freq)
```

- [ ] **Step 6: Update `devices_from_real_decks` to use `attach_real_deck`**

Locate `devices_from_real_decks` in the same file. Replace:

```python
            deck: VirtualDeck = VirtualDeck(config.config(), input, output)
            deck.real_deck = real_deck
            decks.append(deck)
```

with:

```python
            deck: VirtualDeck = VirtualDeck(config.config(), input, output)
            deck.attach_real_deck(real_deck)
            decks.append(deck)
```

- [ ] **Step 7: Add tests**

Append to `tests/test_device_resilience.py`:

```python
class TestVirtualDeckState(unittest.TestCase):
    """Test VirtualDeck.connected lifecycle via lightweight stub.

    We import my_decks_manager by module path and stub out heavy deps.
    """

    @classmethod
    def setUpClass(cls):
        # Build stubs so importing my_decks_manager doesn't require
        # PIL, StreamDeck internals, yaml, etc. that aren't in the test env.
        import types
        pil_mod = types.ModuleType('PIL')
        pil_mod.Image = MagicMock()
        sys.modules.setdefault('PIL', pil_mod)
        sd = MagicMock()
        sd.Devices.StreamDeck.StreamDeck = type('StreamDeck', (), {})
        sd.Devices.StreamDeckPlus.StreamDeckPlus = type(
            'StreamDeckPlus', (),
            {'TOUCHSCREEN_PIXEL_WIDTH': 800, 'TOUCHSCREEN_PIXEL_HEIGHT': 100,
             'TOUCHSCREEN_IMAGE_FORMAT': 'JPEG',
             'TOUCHSCREEN_FLIP': (False, False),
             'TOUCHSCREEN_ROTATION': None})
        sd.DeviceManager.DeviceManager = MagicMock()
        sd.ImageHelpers.PILHelper = MagicMock()
        sys.modules.setdefault('StreamDeck.Devices', sd.Devices)
        sys.modules.setdefault('StreamDeck.Devices.StreamDeck',
                                sd.Devices.StreamDeck)
        sys.modules.setdefault('StreamDeck.Devices.StreamDeckPlus',
                                sd.Devices.StreamDeckPlus)
        sys.modules.setdefault('StreamDeck.DeviceManager', sd.DeviceManager)
        sys.modules.setdefault('StreamDeck.ImageHelpers',
                                sd.ImageHelpers)
        # Now load my_decks_manager
        mdm_path = os.path.join(
            os.path.dirname(__file__), '..', 'src', 'mydeck',
            'my_decks_manager.py')
        spec = importlib.util.spec_from_file_location(
            'mydeck.my_decks_manager', mdm_path)
        mod = importlib.util.module_from_spec(spec)
        sys.modules['mydeck.my_decks_manager'] = mod
        # web_server import inside my_decks_manager needs a stub too
        ws_stub = types.ModuleType('mydeck.web_server')
        ws_stub.DeckOutputWebHandler = MagicMock()
        ws_stub.DeckOutputWebHandler.idDeckMap = {}
        sys.modules.setdefault('mydeck.web_server', ws_stub)
        # lock stub
        lock_stub = types.ModuleType('mydeck.lock')
        class _L:
            @staticmethod
            def do_with_lock(k, fn, wait=0.05):
                fn()
        lock_stub.Lock = _L
        sys.modules.setdefault('mydeck.lock', lock_stub)
        # parent 'mydeck' package stub
        mydeck_pkg = types.ModuleType('mydeck')
        mydeck_pkg.__path__ = [os.path.join(
            os.path.dirname(__file__), '..', 'src', 'mydeck')]
        sys.modules.setdefault('mydeck', mydeck_pkg)
        spec.loader.exec_module(mod)
        cls.mdm = mod

    def _make_vdeck(self):
        VirtualDeck = self.mdm.VirtualDeck
        DeckInput = self.mdm.DeckInput
        DeckOutputWeb = self.mdm.DeckOutputWeb
        opt = {'id': 'r0', 'key_count': 15, 'columns': 5,
               'serial_number': 'SN1'}
        return VirtualDeck(opt, DeckInput({}), DeckOutputWeb({}))

    def test_initial_connected_true_and_no_real_deck(self):
        vd = self._make_vdeck()
        self.assertTrue(vd.connected)
        self.assertFalse(vd.has_real_deck())

    def test_attach_real_deck_sets_has_real_deck(self):
        vd = self._make_vdeck()
        real = MagicMock()
        vd.attach_real_deck(real)
        self.assertTrue(vd.has_real_deck())
        self.assertTrue(vd.connected)

    def test_mark_disconnected_flips_connected_and_notifies(self):
        vd = self._make_vdeck()
        vd.attach_real_deck(MagicMock())
        events = []
        vd.set_lifecycle_listener(lambda v, e: events.append(e))

        vd.mark_disconnected()

        self.assertFalse(vd.connected)
        self.assertEqual(events, ['disconnected'])

    def test_mark_disconnected_is_idempotent(self):
        vd = self._make_vdeck()
        vd.attach_real_deck(MagicMock())
        events = []
        vd.set_lifecycle_listener(lambda v, e: events.append(e))

        vd.mark_disconnected()
        vd.mark_disconnected()

        self.assertEqual(events, ['disconnected'])

    def test_reattach_restores_callbacks_and_brightness(self):
        vd = self._make_vdeck()
        vd.attach_real_deck(MagicMock())
        cb = lambda d, k, s: None
        vd.set_key_callback(cb)
        vd.set_brightness(50)
        vd.mark_disconnected()
        events = []
        vd.set_lifecycle_listener(lambda v, e: events.append(e))

        new_real = MagicMock()
        vd.reattach(new_real)

        self.assertTrue(vd.connected)
        new_real.set_key_callback.assert_called_once_with(cb)
        new_real.set_brightness.assert_called_once_with(50)
        self.assertEqual(events, ['reconnected'])
```

- [ ] **Step 8: Run tests**

```bash
python3 -m pytest tests/test_device_resilience.py -v
```

Expected: all pass.

- [ ] **Step 9: Commit**

```bash
git add src/mydeck/my_decks_manager.py tests/test_device_resilience.py
git commit -m "feat(resilience): VirtualDeck tracks connected state + reattach support"
```

---

## Task 5: DeviceSupervisor — polling loop (TDD)

**Files:**
- Modify: `src/mydeck/device_resilience.py`
- Modify: `tests/test_device_resilience.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_device_resilience.py`:

```python
DeviceSupervisor = _mod.DeviceSupervisor


class FakeManagerVDeck:
    """Stand-in for VirtualDeck used by DeviceSupervisor tests."""
    def __init__(self, serial, has_real=True, connected=True):
        self.serial = serial
        self._has_real = has_real
        self.connected = connected
        self.reattach_with = None

    def get_serial_number(self):
        return self.serial

    def has_real_deck(self):
        return self._has_real

    def reattach(self, real_deck):
        self.reattach_with = real_deck
        self.connected = True


class TestDeviceSupervisor(unittest.TestCase):
    def _enumerator(self, by_tick):
        """Return a function that returns by_tick[i] on call i (clamped)."""
        calls = {'i': 0}
        def enum():
            i = min(calls['i'], len(by_tick) - 1)
            calls['i'] += 1
            return by_tick[i]
        return enum

    def test_reconnect_matches_by_serial_and_calls_reattach(self):
        vd = FakeManagerVDeck('SN1', has_real=True, connected=False)
        new_real = MagicMock()
        new_real.get_serial_number.return_value = 'SN1'
        enum = lambda: [new_real]
        opener = lambda rd: None  # rd.open() no-op

        sup = DeviceSupervisor([vd], enumerator=enum, opener=opener,
                               interval=0.01)
        sup.tick_once()

        self.assertEqual(vd.reattach_with, new_real)
        self.assertTrue(vd.connected)

    def test_unknown_serial_is_ignored(self):
        vd = FakeManagerVDeck('SN1', has_real=True, connected=False)
        other = MagicMock()
        other.get_serial_number.return_value = 'SN_OTHER'

        sup = DeviceSupervisor([vd], enumerator=lambda: [other],
                               opener=lambda rd: None, interval=0.01)
        sup.tick_once()

        self.assertIsNone(vd.reattach_with)
        self.assertFalse(vd.connected)

    def test_already_connected_deck_is_skipped(self):
        vd = FakeManagerVDeck('SN1', has_real=True, connected=True)
        rd = MagicMock()
        rd.get_serial_number.return_value = 'SN1'

        sup = DeviceSupervisor([vd], enumerator=lambda: [rd],
                               opener=lambda r: None, interval=0.01)
        sup.tick_once()

        self.assertIsNone(vd.reattach_with)

    def test_open_failure_leaves_disconnected(self):
        vd = FakeManagerVDeck('SN1', has_real=True, connected=False)
        rd = MagicMock()
        rd.get_serial_number.return_value = 'SN1'
        def opener(r):
            raise TransportError("busy")

        sup = DeviceSupervisor([vd], enumerator=lambda: [rd],
                               opener=opener, interval=0.01)
        sup.tick_once()

        self.assertIsNone(vd.reattach_with)
        self.assertFalse(vd.connected)

    def test_virtual_only_deck_is_skipped(self):
        vd = FakeManagerVDeck('VIRT1', has_real=False, connected=True)
        rd = MagicMock()
        rd.get_serial_number.return_value = 'VIRT1'

        sup = DeviceSupervisor([vd], enumerator=lambda: [rd],
                               opener=lambda r: None, interval=0.01)
        sup.tick_once()

        self.assertIsNone(vd.reattach_with)
```

- [ ] **Step 2: Run — expect FAIL**

```bash
python3 -m pytest tests/test_device_resilience.py::TestDeviceSupervisor -v
```

Expected: FAIL (`DeviceSupervisor` not defined).

- [ ] **Step 3: Add DeviceSupervisor to device_resilience.py**

Append to `src/mydeck/device_resilience.py`:

```python
import threading


class DeviceSupervisor:
    """Periodically re-enumerate physical devices and reattach matching serials.

    The supervisor is a daemon thread. Dependency injection keeps tests fast:
    `enumerator` returns the current list of physical deck handles (same shape
    as `DeviceManager().enumerate()`); `opener` is a callable that opens a
    freshly-enumerated deck (default: `real_deck.open()`).
    """

    def __init__(self, virtual_decks, enumerator=None, opener=None,
                 interval: float = 3.0):
        self._vdecks = list(virtual_decks)
        if enumerator is None:
            from StreamDeck.DeviceManager import DeviceManager
            enumerator = lambda: DeviceManager().enumerate()
        if opener is None:
            opener = lambda rd: rd.open()
        self._enumerator = enumerator
        self._opener = opener
        self._interval = interval
        self._stop_event = threading.Event()
        self._thread = None

    def add_virtual_deck(self, vdeck) -> None:
        self._vdecks.append(vdeck)

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._thread = threading.Thread(
            target=self._run, daemon=True, name='DeviceSupervisor')
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()

    def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                self.tick_once()
            except Exception as e:
                logging.error("DeviceSupervisor tick error: %s", e)
            self._stop_event.wait(self._interval)

    def tick_once(self) -> None:
        """Run one enumerate+reattach pass. Exposed for unit tests."""
        targets = [vd for vd in self._vdecks
                   if vd.has_real_deck() and not vd.connected]
        if not targets:
            return
        try:
            enumerated = list(self._enumerator())
        except Exception as e:
            logging.error("enumerate failed: %s", e)
            return
        by_serial = {}
        for rd in enumerated:
            try:
                sn = rd.get_serial_number()
            except Exception:
                continue
            by_serial[sn] = rd
        for vd in targets:
            sn = vd.get_serial_number()
            rd = by_serial.get(sn)
            if rd is None:
                continue
            try:
                self._opener(rd)
            except (TransportError, OSError) as e:
                logging.info(
                    "reconnect open failed for %s: %s (will retry)", sn, e)
                continue
            try:
                vd.reattach(rd)
                logging.info("device %s reconnected", sn)
            except Exception as e:
                logging.error("reattach failed for %s: %s", sn, e)
```

- [ ] **Step 4: Run tests**

```bash
python3 -m pytest tests/test_device_resilience.py -v
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add src/mydeck/device_resilience.py tests/test_device_resilience.py
git commit -m "feat(resilience): add DeviceSupervisor polling thread"
```

---

## Task 6: MyDeck — on_disconnect/on_reconnect hooks (TDD)

**Files:**
- Modify: `src/mydeck/my_decks.py`
- Modify: `tests/test_device_resilience.py`

- [ ] **Step 1: Add failing test**

Append to `tests/test_device_resilience.py`:

```python
class TestMyDeckDisconnectHooks(unittest.TestCase):
    """Verify on_disconnect/on_reconnect behavior in isolation using a
    lightweight stand-in rather than loading the full my_decks module
    (which pulls in wand, cairosvg, etc.)."""

    def test_hooks_save_and_restore_page(self):
        # Inline minimal clone of the hook methods we will add to MyDeck.
        class MyDeckLike:
            def __init__(self):
                self._current_page = '@HOME'
                self._pre_disconnect_page = None
                self.calls = []

            def current_page(self):
                return self._current_page

            def set_current_page(self, name, add_previous=True):
                self.calls.append((name, add_previous))
                self._current_page = name

            # Methods we'll define in my_decks.py for real:
            def on_disconnect(self):
                if self._current_page == '~DISCONNECTED':
                    return
                self._pre_disconnect_page = self._current_page
                self.set_current_page('~DISCONNECTED', add_previous=False)

            def on_reconnect(self):
                target = self._pre_disconnect_page or '@HOME'
                self._pre_disconnect_page = None
                self.set_current_page(target, add_previous=False)

        md = MyDeckLike()
        md._current_page = '@JOB'
        md.on_disconnect()
        self.assertEqual(md._current_page, '~DISCONNECTED')
        self.assertEqual(md._pre_disconnect_page, '@JOB')

        md.on_reconnect()
        self.assertEqual(md._current_page, '@JOB')
        self.assertIsNone(md._pre_disconnect_page)
```

- [ ] **Step 2: Run — expect PASS (this test is self-contained)**

```bash
python3 -m pytest tests/test_device_resilience.py::TestMyDeckDisconnectHooks -v
```

Expected: PASS. (This pins the intended hook behavior as a spec; the real MyDeck methods implemented below must match.)

- [ ] **Step 3: Add hooks to MyDeck in `my_decks.py`**

Locate the `MyDeck` class. In `__init__`, find:

```python
        self._current_page: str = '@HOME'
        self._previous_pages: list[str] = ['@HOME']
```

Add a line right after:

```python
        self._pre_disconnect_page: Optional[str] = None
```

Then add these methods to `MyDeck` (place them near `set_current_page`):

```python
    def on_disconnect(self) -> None:
        """Called when the physical device is detected as disconnected.

        Saves the current page and switches to the reserved ``~DISCONNECTED``
        page, which has no keys/apps; existing app threads observe this via
        ``check_to_stop`` and exit cleanly.
        """
        if self._current_page == '~DISCONNECTED':
            return
        self._pre_disconnect_page = self._current_page
        logging.info("[%s] device disconnected; saving page %s",
                     self.deck.id(), self._current_page)
        self.set_current_page('~DISCONNECTED', add_previous=False)

    def on_reconnect(self) -> None:
        """Called when the physical device is re-attached via supervisor.

        Restores the page that was active before disconnect so the
        normal page-change machinery re-spawns foreground apps and
        re-renders key images.
        """
        target: str = self._pre_disconnect_page or '@HOME'
        self._pre_disconnect_page = None
        logging.info("[%s] device reconnected; restoring page %s",
                     self.deck.id(), target)
        # deck.reset and set_brightness will go through DeckGuard; safe either
        # way. set_current_page triggers threading_apps + key_touchscreen_setup.
        try:
            self.deck.reset()
        except Exception as e:
            logging.error("reset on reconnect failed: %s", e)
        self.set_current_page(target, add_previous=False)
```

- [ ] **Step 4: Ensure `set_current_page` accepts `~DISCONNECTED`**

Locate in `my_decks.py`:

```python
    def set_current_page(self, name: str, add_previous: bool = True):
        """Set given page name as current_page and setup keys."""
        if name[0] != "~ALERT":
            self.set_alert_off()
```

That's already fine — the only special-case is `~ALERT`. `~DISCONNECTED` will flow through normal page setup; since its `key_config`/`touch_config`/`dial_config` return `None` (page not defined), `key_touchscreen_setup` just does nothing — which is what we want.

No change needed here. Verify by reading the method.

- [ ] **Step 5: Run tests**

```bash
python3 -m pytest tests/test_device_resilience.py -v
```

Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add src/mydeck/my_decks.py tests/test_device_resilience.py
git commit -m "feat(resilience): MyDeck.on_disconnect/on_reconnect page lifecycle"
```

---

## Task 7: Wire lifecycle events into start_decks

**Files:**
- Modify: `src/mydeck/my_decks.py`
- Modify: `src/mydeck/my_decks_manager.py`

- [ ] **Step 1: Register listener + start supervisor in `start_decks`**

In `src/mydeck/my_decks.py`, locate the `start_decks` method on `MyDecks`. After the `for index, deck in enumerate(streamdecks)` loop completes and before `def stop_decks(signal, frame):`, add:

```python
        # Wire device resilience: each VirtualDeck gets a lifecycle listener
        # that dispatches to the owning MyDeck. A single DeviceSupervisor
        # thread re-enumerates every 3s to detect reconnects.
        from .device_resilience import DeviceSupervisor

        def _dispatch(vdeck, event):
            mydeck = None
            for md in self.mydecks.values():
                if md.deck is vdeck:
                    mydeck = md
                    break
            if mydeck is None:
                return
            if event == 'disconnected':
                mydeck.on_disconnect()
            elif event == 'reconnected':
                mydeck.on_reconnect()

        for md in self.mydecks.values():
            md.deck.set_lifecycle_listener(_dispatch)

        self._device_supervisor = DeviceSupervisor(
            [md.deck for md in self.mydecks.values()])
        self._device_supervisor.start()
```

- [ ] **Step 2: Stop supervisor in `stop_decks`**

In the nested `stop_decks` function, add at the top (before `DeckOutputWebServer.shutdown()`):

```python
            if getattr(self, '_device_supervisor', None) is not None:
                self._device_supervisor.stop()
```

- [ ] **Step 3: Smoke test: start mydeck with only virtual decks**

```bash
cd /home/ktat/git/github/mystreamdeck
PYTHONPATH=src python3 -c "
import logging
logging.basicConfig(level=logging.INFO)
from mydeck import MyDecks
print('import OK')
"
```

Expected: `import OK` (no ModuleNotFoundError).

- [ ] **Step 4: Run full test suite**

```bash
python3 -m pytest tests/ -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/mydeck/my_decks.py
git commit -m "feat(resilience): start DeviceSupervisor from MyDecks.start_decks"
```

---

## Task 8: Startup without device — create VirtualDeck for known unattached serials

**Files:**
- Modify: `src/mydeck/my_decks_manager.py`
- Modify: `src/mydeck/my_decks.py`
- Modify: `tests/test_device_resilience.py`

**Goal:** If `configs` names a serial the user has previously configured but the device isn't plugged in at startup, still create a `VirtualDeck` in `connected=False` state so supervisor can reattach later.

- [ ] **Step 1: Add failing integration-style test**

Append to `tests/test_device_resilience.py`:

```python
class TestMyDecksManagerStartupWithoutDevice(unittest.TestCase):
    """MyDecksManager should allow seeding decks for known serials even if
    enumerate() returns an empty list at startup."""

    @classmethod
    def setUpClass(cls):
        cls.mdm = sys.modules.get('mydeck.my_decks_manager')
        if cls.mdm is None:
            # imported by the VirtualDeckState setUp — but be safe
            raise RuntimeError(
                "my_decks_manager should be pre-loaded by earlier test")

    def test_seed_creates_disconnected_vdeck(self):
        mdm = self.mdm
        # No virtual config file, no real decks, but `known_serials` passed.
        manager = mdm.MyDecksManager(
            None, no_real_device=True, known_serials={
                'SN_KNOWN': {'key_count': 15, 'columns': 5,
                             'has_touchscreen': False, 'dial_count': 0}
            })
        self.assertEqual(len(manager.devices), 1)
        vd = manager.devices[0]
        self.assertEqual(vd.get_serial_number(), 'SN_KNOWN')
        self.assertTrue(vd.has_real_deck())   # marked as physical-backed
        self.assertFalse(vd.connected)        # but not attached yet
```

- [ ] **Step 2: Run — expect FAIL**

```bash
python3 -m pytest tests/test_device_resilience.py::TestMyDecksManagerStartupWithoutDevice -v
```

Expected: FAIL (`known_serials` kwarg doesn't exist).

- [ ] **Step 3: Add `known_serials` param to `MyDecksManager.__init__`**

In `src/mydeck/my_decks_manager.py`, replace `MyDecksManager.__init__`:

```python
    def __init__(self, config_file: str, no_real_device: bool = False,
                 known_serials: Optional[dict] = None):
        """Pass configration file for veirtual decks, and flag as 2nd argument if you have no real STREAM DECK device.

        known_serials: optional dict mapping serial -> {key_count, columns,
        has_touchscreen, dial_count}. For each serial not currently enumerated,
        a VirtualDeck is created in connected=False state so DeviceSupervisor
        can later reattach the real device.
        """
        real_decks: list[StreamDeck] = []
        self.devices: list = []
        if config_file is not None:
            self.devices = self.devices_from_config(config_file)
        enumerated_serials: set = set()
        if no_real_device is False:
            real_decks = DeviceManager().enumerate()
            if len(real_decks) > 0:
                self.devices[len(self.devices):] = self.devices_from_real_decks(
                    real_decks)
                for rd in real_decks:
                    try:
                        enumerated_serials.add(rd.get_serial_number())
                    except Exception:
                        pass
        if known_serials:
            self.devices[len(self.devices):] = self.devices_from_known_serials(
                known_serials, exclude=enumerated_serials)
```

- [ ] **Step 4: Add `devices_from_known_serials` method**

Add to `MyDecksManager` (after `devices_from_real_decks`):

```python
    def devices_from_known_serials(self, known_serials: dict,
                                   exclude: set) -> list['VirtualDeck']:
        """Create disconnected VirtualDecks for serials not currently
        enumerated, so supervisor can reattach once they appear."""
        decks: list[VirtualDeck] = []
        i: int = len(self.devices)
        for sn, spec in known_serials.items():
            if sn in exclude:
                continue
            opt = {
                'key_count': spec.get('key_count', 15),
                'columns': spec.get('columns', 5),
                'serial_number': sn,
                'has_touchscreen': spec.get('has_touchscreen', False),
                'dial_count': spec.get('dial_count', 0),
            }
            config = VirtualDeckConfig('k' + str(i), opt)
            input = DeckInput.FromOption({})
            output = DeckOutputWeb({})
            deck: VirtualDeck = VirtualDeck(config.config(), input, output)
            # Mark as physical-backed but not currently connected.
            deck._has_real_deck = True
            deck.connected = False
            decks.append(deck)
            MyDecksManager.ConfigQueue[sn] = queue.Queue()
            i += 1
        return decks
```

- [ ] **Step 5: Thread `known_serials` through MyDecks.start_decks**

In `src/mydeck/my_decks.py`, replace this line in `start_decks`:

```python
        streamdecks = MyDecksManager(self.vdeck_config, no_real_device).devices
```

with:

```python
        known_serials: dict = {}
        if self.configs is not None:
            for sn in self.configs.keys():
                # We don't know key_count/columns yet — use defaults and let
                # reattach() fix up the real values from the attached device.
                known_serials[sn] = {'key_count': 15, 'columns': 5}
        manager = MyDecksManager(
            self.vdeck_config, no_real_device,
            known_serials=known_serials)
        streamdecks = manager.devices
```

Wait — `self.configs` in `MyDecks` is keyed by **name alias**, not serial. The mapping is:
- `self.decks`: `{serial_number: name_alias}`
- `self.configs`: `{name_alias: {file: ..., alert_func: ...}}`

So to get serials: iterate `self.decks.keys()`.

Replace instead with:

```python
        known_serials: dict = {}
        if self.decks is not None:
            for sn in self.decks.keys():
                known_serials[sn] = {'key_count': 15, 'columns': 5}
        manager = MyDecksManager(
            self.vdeck_config, no_real_device,
            known_serials=known_serials)
        streamdecks = manager.devices
```

**Note:** `key_count=15, columns=5` are placeholder defaults used only until the device is attached. The real values come from the physical device during `reattach`. See Task 9 for the fix-up.

- [ ] **Step 6: Run tests**

```bash
python3 -m pytest tests/test_device_resilience.py -v
```

Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add src/mydeck/my_decks_manager.py src/mydeck/my_decks.py tests/test_device_resilience.py
git commit -m "feat(resilience): seed VirtualDeck for known-but-unattached serials"
```

---

## Task 9: reattach updates device specs from real device

**Files:**
- Modify: `src/mydeck/my_decks_manager.py`
- Modify: `tests/test_device_resilience.py`

**Why:** When Task 8 seeded a VirtualDeck with placeholder `key_count=15, columns=5`, the real device may be different (e.g., StreamDeck Mini has 6 keys). On reattach, pick up the real values.

- [ ] **Step 1: Add failing test**

Append to `tests/test_device_resilience.py`:

```python
class TestReattachUpdatesSpecs(unittest.TestCase):
    def test_reattach_updates_key_count_from_real_deck(self):
        mdm = sys.modules.get('mydeck.my_decks_manager')
        VirtualDeck = mdm.VirtualDeck
        DeckInput = mdm.DeckInput
        DeckOutputWeb = mdm.DeckOutputWeb
        opt = {'id': 'k0', 'key_count': 15, 'columns': 5,
               'serial_number': 'SN1'}
        vd = VirtualDeck(opt, DeckInput({}), DeckOutputWeb({}))
        vd._has_real_deck = True
        vd.connected = False

        real = MagicMock()
        real.KEY_COUNT = 6
        real.KEY_COLS = 3
        real.get_serial_number.return_value = 'SN1'

        vd.reattach(real)

        self.assertEqual(vd.key_count(), 6)
        self.assertEqual(vd.columns(), 3)
```

- [ ] **Step 2: Run — expect FAIL**

```bash
python3 -m pytest tests/test_device_resilience.py::TestReattachUpdatesSpecs -v
```

Expected: FAIL (key_count still 15).

- [ ] **Step 3: Update `reattach` to pick up device specs**

In `src/mydeck/my_decks_manager.py`, in `VirtualDeck.reattach`, right after `self._guard._set_real_deck(real_deck)`:

```python
            self._guard._set_real_deck(real_deck)
            # Pick up actual device dimensions (Task 8 seeded placeholders).
            try:
                self._key_count = int(getattr(real_deck, 'KEY_COUNT',
                                               self._key_count))
                self._columns = int(getattr(real_deck, 'KEY_COLS',
                                             self._columns))
            except Exception as e:
                logging.error("reattach spec update failed: %s", e)
            self._has_real_deck = True
            self.connected = True
```

- [ ] **Step 4: Run tests**

```bash
python3 -m pytest tests/test_device_resilience.py -v
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add src/mydeck/my_decks_manager.py tests/test_device_resilience.py
git commit -m "feat(resilience): reattach syncs key_count/columns from real device"
```

---

## Task 10: Handle Web UI exit button during disconnect

**Files:**
- Modify: `src/mydeck/my_decks.py`
- Modify: `tests/test_device_resilience.py`

**Why:** `key_change_callback` (my_decks.py:726) uses `with deck:` and calls `deck.reset()` / `deck.close()`. During disconnect these are no-ops (good), but the exit path calls `sys.exit()` which we want to keep working. This task just verifies no regression — no code change needed if `DeckGuard` context manager is correct.

- [ ] **Step 1: Add sanity test**

Append to `tests/test_device_resilience.py`:

```python
class TestGuardWhenDisconnectedExitFlow(unittest.TestCase):
    def test_with_statement_on_disconnected_guard_is_noop(self):
        vd = FakeVirtualDeck()
        vd.connected = False
        guard = DeckGuard(vd)
        real = MagicMock()
        guard._set_real_deck(real)

        # Disconnect → with block should not raise, and real.reset should
        # be a no-op via guard (never called on the real object).
        with guard:
            guard.reset()
            guard.close()

        real.reset.assert_not_called()
        real.close.assert_not_called()
        # Context manager itself does delegate __enter__/__exit__ though.
        real.__enter__.assert_called_once()
        real.__exit__.assert_called_once()
```

- [ ] **Step 2: Run**

```bash
python3 -m pytest tests/test_device_resilience.py::TestGuardWhenDisconnectedExitFlow -v
```

Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add tests/test_device_resilience.py
git commit -m "test(resilience): exit path during disconnect does not crash"
```

---

## Task 11: Integration test — end-to-end disconnect/reconnect

**Files:**
- Modify: `tests/test_device_resilience.py`

- [ ] **Step 1: Add integration test**

Append to `tests/test_device_resilience.py`:

```python
class TestEndToEndDisconnectReconnect(unittest.TestCase):
    """Simulate a full disconnect→reconnect cycle using stubbed deps.

    Flow:
      1. VirtualDeck attached to a real_deck (MagicMock)
      2. real_deck raises TransportError on set_key_image
      3. DeckGuard catches it → mark_disconnected → listener fires
      4. Listener switches to ~DISCONNECTED
      5. Supervisor tick enumerates a new real_deck with same serial
      6. reattach fires → listener fires 'reconnected' → restore page
    """

    def test_full_cycle(self):
        mdm = sys.modules.get('mydeck.my_decks_manager')
        VirtualDeck = mdm.VirtualDeck
        DeckInput = mdm.DeckInput
        DeckOutputWeb = mdm.DeckOutputWeb

        opt = {'id': 'e1', 'key_count': 15, 'columns': 5,
               'serial_number': 'SN_E2E'}
        vd = VirtualDeck(opt, DeckInput({}), DeckOutputWeb({}))

        real1 = MagicMock()
        real1.get_serial_number.return_value = 'SN_E2E'
        real1.set_key_image.side_effect = TransportError("usb gone")
        vd.attach_real_deck(real1)

        # Fake MyDeck behavior via listener
        page_state = {'page': '@JOB', 'saved': None}

        def listener(v, event):
            if event == 'disconnected':
                page_state['saved'] = page_state['page']
                page_state['page'] = '~DISCONNECTED'
            elif event == 'reconnected':
                page_state['page'] = page_state['saved']
                page_state['saved'] = None

        vd.set_lifecycle_listener(listener)

        # 1. App tries to draw → TransportError → disconnect
        vd.real_deck.set_key_image(0, 'img')
        self.assertFalse(vd.connected)
        self.assertEqual(page_state['page'], '~DISCONNECTED')

        # 2. Supervisor sees new device with same serial
        real2 = MagicMock()
        real2.get_serial_number.return_value = 'SN_E2E'
        real2.KEY_COUNT = 15
        real2.KEY_COLS = 5

        sup = DeviceSupervisor([vd], enumerator=lambda: [real2],
                               opener=lambda r: None, interval=0.01)
        sup.tick_once()

        self.assertTrue(vd.connected)
        self.assertEqual(page_state['page'], '@JOB')
        # Subsequent I/O goes to the new real_deck
        vd.real_deck.set_key_image(1, 'img2')
        real2.set_key_image.assert_called_once_with(1, 'img2')
```

- [ ] **Step 2: Run**

```bash
python3 -m pytest tests/test_device_resilience.py -v
```

Expected: all pass.

- [ ] **Step 3: Commit**

```bash
git add tests/test_device_resilience.py
git commit -m "test(resilience): end-to-end disconnect/reconnect cycle"
```

---

## Task 12: Manual verification

**Files:** (none)

- [ ] **Step 1: Virtual-only smoke test**

```bash
cd /home/ktat/git/github/mystreamdeck
PYTHONPATH=src python3 example/main_virtual.py
```

Expected: web server starts at `http://localhost:3000`, no stack traces, INFO log shows `DeviceSupervisor` thread name in tick logs (or absence of devices — supervisor no-ops when no physical decks).

Press Ctrl-C to stop.

- [ ] **Step 2: Real device test — plug out/in**

With a physical STREAM DECK connected:

```bash
mydeck
```

- Wait for initial page render.
- Physically unplug the USB cable.
- Observe logs: `INFO ... device SN disconnected ...`; `INFO ... device disconnected; saving page ...`. No stack trace, no process exit.
- Plug back in.
- Within ~3 seconds observe: `INFO ... device SN reconnected`; `INFO ... device reconnected; restoring page ...`. Original page/apps return.

- [ ] **Step 3: Sleep/resume test**

With mydeck running and a real device attached, suspend the laptop (`systemctl suspend`), wait 10s, wake it. Expect the same disconnect/reconnect log sequence (sleep typically drops USB) and automatic return to the same page.

- [ ] **Step 4: Startup-without-device test**

With a real STREAM DECK not plugged in, and `~/.config/mydeck/<SERIAL>.yml` already present from a previous session:

```bash
mydeck
```

Expected: starts without prompting for virtual deck creation (known serial seeds a disconnected VirtualDeck), Web UI comes up, logs show no crash. Plug the device → within 3 seconds it reconnects and renders.

- [ ] **Step 5: Unknown-serial ignored**

Plug a different STREAM DECK (different serial) into a running mydeck. Expect: no crash, no UI change, enumerate log shows unknown serial skipped (at DEBUG — if you want to see it, run with `--log-level DEBUG`).

- [ ] **Step 6: Commit the completed checklist**

```bash
git commit --allow-empty -m "chore(resilience): manual verification completed"
```

---

## Completion

All tasks complete → the implementation matches the spec at `docs/superpowers/specs/2026-04-17-device-resilience-design.md`. Expected behavior:

- USB unplug / laptop sleep: no crash; foreground apps stop cleanly; background apps keep running (I/O silently no-op).
- Reattach (same serial) within 3 seconds: apps restart on the pre-disconnect page; keys/touchscreen re-render.
- Startup without device (but known serial in configs): mydeck starts in disconnected state; attaches when device appears.
- Unknown serial at runtime: ignored.
