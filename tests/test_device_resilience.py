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


if __name__ == '__main__':
    unittest.main()
