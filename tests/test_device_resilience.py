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
        new_real.reset.assert_called_once()  # NEW assertion
        new_real.set_key_callback.assert_called_once_with(cb)
        new_real.set_brightness.assert_called_once_with(50)
        self.assertEqual(events, ['reconnected'])


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

    def test_reconnect_opens_before_reading_serial(self):
        """Regression: get_serial_number must be called AFTER open()."""
        vd = FakeManagerVDeck('SN1', has_real=True, connected=False)
        rd = MagicMock()
        call_order = []
        rd.open.side_effect = lambda: call_order.append('open')
        rd.get_serial_number.side_effect = (
            lambda: call_order.append('serial') or 'SN1')

        sup = DeviceSupervisor([vd], enumerator=lambda: [rd],
                               opener=lambda r: r.open(), interval=0.01)
        sup.tick_once()

        self.assertEqual(call_order, ['open', 'serial'])
        self.assertIsNotNone(vd.reattach_with)

    def test_non_matching_candidate_is_closed(self):
        """Candidates whose serial doesn't match any target should be closed."""
        vd = FakeManagerVDeck('SN1', has_real=True, connected=False)
        rd_other = MagicMock()
        rd_other.get_serial_number.return_value = 'SN_OTHER'

        sup = DeviceSupervisor([vd], enumerator=lambda: [rd_other],
                               opener=lambda r: None, interval=0.01)
        sup.tick_once()

        rd_other.close.assert_called_once()
        self.assertIsNone(vd.reattach_with)


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


class TestEndToEndDisconnectReconnect(unittest.TestCase):
    """Simulate a full disconnect→reconnect cycle using stubbed deps."""

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


class TestGuardReadsWhenDisconnected(unittest.TestCase):
    def test_deck_type_returns_none_when_no_real_deck(self):
        vd = FakeVirtualDeck()
        guard = DeckGuard(vd)
        # _set_real_deck never called
        self.assertIsNone(guard.deck_type())

    def test_deck_type_returns_none_when_disconnected(self):
        vd = FakeVirtualDeck()
        vd.connected = False
        real = MagicMock()
        real.deck_type.return_value = 'StreamDeckXL'
        guard = DeckGuard(vd)
        guard._set_real_deck(real)
        self.assertIsNone(guard.deck_type())
        real.deck_type.assert_not_called()


class TestNoDuplicateSeeding(unittest.TestCase):
    """Regression test for bug where known_serials seeded duplicates of
    VirtualDecks already created from vdeck_config."""

    @classmethod
    def setUpClass(cls):
        mdm = sys.modules.get('mydeck.my_decks_manager')
        if mdm is None:
            # Alphabetical ordering placed us before TestVirtualDeckState;
            # load the module ourselves using the same stub approach.
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
            sys.modules.setdefault('StreamDeck.ImageHelpers', sd.ImageHelpers)
            ws_stub = types.ModuleType('mydeck.web_server')
            ws_stub.DeckOutputWebHandler = MagicMock()
            ws_stub.DeckOutputWebHandler.idDeckMap = {}
            sys.modules.setdefault('mydeck.web_server', ws_stub)
            lock_stub = types.ModuleType('mydeck.lock')
            class _L:
                @staticmethod
                def do_with_lock(k, fn, wait=0.05):
                    fn()
            lock_stub.Lock = _L
            sys.modules.setdefault('mydeck.lock', lock_stub)
            mydeck_pkg = types.ModuleType('mydeck')
            mydeck_pkg.__path__ = [os.path.join(
                os.path.dirname(__file__), '..', 'src', 'mydeck')]
            sys.modules.setdefault('mydeck', mydeck_pkg)
            mdm_path = os.path.join(
                os.path.dirname(__file__), '..', 'src', 'mydeck',
                'my_decks_manager.py')
            spec = importlib.util.spec_from_file_location(
                'mydeck.my_decks_manager', mdm_path)
            mod = importlib.util.module_from_spec(spec)
            sys.modules['mydeck.my_decks_manager'] = mod
            spec.loader.exec_module(mod)
            mdm = mod
        cls.mdm = mdm

    def test_vdeck_config_serials_excluded_from_known_serials(self):
        import tempfile
        import yaml
        mdm = self.mdm
        with tempfile.NamedTemporaryFile(
                mode='w', suffix='.yml', delete=False) as f:
            yaml.dump({
                1: {'key_count': 4, 'columns': 2,
                    'serial_number': 'VDECK_SN1'},
            }, f)
            vdeck_config_path = f.name

        try:
            manager = mdm.MyDecksManager(
                vdeck_config_path, no_real_device=True,
                known_serials={
                    'VDECK_SN1': {'key_count': 15, 'columns': 5},
                    'PHYS_SN2': {'key_count': 15, 'columns': 5},
                })
            serials = sorted(d.get_serial_number() for d in manager.devices)
            self.assertEqual(serials, ['PHYS_SN2', 'VDECK_SN1'])
        finally:
            os.unlink(vdeck_config_path)


class TestSupervisorSkipsHealthyPaths(unittest.TestCase):
    def test_connected_device_path_is_not_probed(self):
        """Supervisor must not open/close the HID handle of a still-healthy
        deck every tick — doing so interferes with its writes."""
        # Connected VDeck with a known path on its real_deck
        healthy_vd = FakeManagerVDeck('SN_HEALTHY', has_real=True,
                                      connected=True)
        # Fake _guard._get_real_deck chain returning path info
        inner_real = MagicMock()
        inner_real.device.device_info = {'path': b'/dev/hidraw0'}
        healthy_vd._guard = MagicMock()
        healthy_vd._guard._get_real_deck = MagicMock(return_value=inner_real)

        # Disconnected target
        disconnected_vd = FakeManagerVDeck('SN_DISCONN', has_real=True,
                                            connected=False)

        # Enumerate returns both — with same path as healthy one and a new one
        rd_healthy = MagicMock()
        rd_healthy.device.device_info = {'path': b'/dev/hidraw0'}
        rd_new = MagicMock()
        rd_new.device.device_info = {'path': b'/dev/hidraw1'}
        rd_new.get_serial_number.return_value = 'SN_DISCONN'

        sup = DeviceSupervisor([healthy_vd, disconnected_vd],
                               enumerator=lambda: [rd_healthy, rd_new],
                               opener=lambda r: None, interval=0.01)
        sup.tick_once()

        # Healthy device was NOT opened or closed
        rd_healthy.open.assert_not_called()
        rd_healthy.close.assert_not_called()
        # New device WAS opened and reattached
        self.assertEqual(disconnected_vd.reattach_with, rd_new)


if __name__ == '__main__':
    unittest.main()
