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
        new_real.set_key_callback.assert_called_once_with(cb)
        new_real.set_brightness.assert_called_once_with(50)
        self.assertEqual(events, ['reconnected'])


if __name__ == '__main__':
    unittest.main()
