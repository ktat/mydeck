import importlib.util
import json
import os
import sys
import tempfile
import time
import unittest
from unittest.mock import MagicMock, patch

# Patch keyring before any import touches it
keyring_mock = MagicMock()
sys.modules['keyring'] = keyring_mock

# Load totp_account_manager directly to avoid triggering mydeck/__init__.py
# which pulls in StreamDeck, wand, cairosvg etc. that are not installed in test env.
_module_path = os.path.join(os.path.dirname(__file__), '..', 'src', 'mydeck', 'totp_account_manager.py')
_spec = importlib.util.spec_from_file_location('mydeck.totp_account_manager', _module_path)
_mod = importlib.util.module_from_spec(_spec)
sys.modules['mydeck.totp_account_manager'] = _mod
_spec.loader.exec_module(_mod)

TotpAccountManager = _mod.TotpAccountManager
KEYRING_SERVICE = _mod.KEYRING_SERVICE


class TestTotpAccountManager(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.accounts_file = os.path.join(self.tmpdir, 'accounts.json')
        self.manager = TotpAccountManager(accounts_file=self.accounts_file)
        keyring_mock.reset_mock()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    # --- load_accounts ---

    def test_load_accounts_returns_empty_list_when_file_missing(self):
        result = self.manager.load_accounts()
        self.assertEqual(result, [])

    def test_load_accounts_returns_saved_accounts(self):
        data = [{"name": "GitHub", "issuer": "GitHub"}]
        with open(self.accounts_file, 'w') as f:
            json.dump(data, f)
        self.assertEqual(self.manager.load_accounts(), data)

    # --- save_account ---

    def test_save_account_writes_to_json_and_keyring(self):
        self.manager.save_account("GitHub", "GitHub", "JBSWY3DPEHPK3PXP")
        accounts = self.manager.load_accounts()
        self.assertEqual(len(accounts), 1)
        self.assertEqual(accounts[0]['name'], 'GitHub')
        self.assertEqual(accounts[0]['issuer'], 'GitHub')
        keyring_mock.set_password.assert_called_with(
            KEYRING_SERVICE, "GitHub", "JBSWY3DPEHPK3PXP"
        )

    def test_save_account_updates_existing_without_duplicate(self):
        self.manager.save_account("GitHub", "GitHub", "SECRET1")
        keyring_mock.reset_mock()
        self.manager.save_account("GitHub", "GitHub", "SECRET2")
        accounts = self.manager.load_accounts()
        self.assertEqual(len(accounts), 1)
        keyring_mock.set_password.assert_called_with(KEYRING_SERVICE, "GitHub", "SECRET2")

    def test_save_account_adds_multiple_accounts(self):
        self.manager.save_account("GitHub", "GitHub", "SECRET1")
        self.manager.save_account("Google", "Google", "SECRET2")
        accounts = self.manager.load_accounts()
        self.assertEqual(len(accounts), 2)

    # --- delete_account ---

    def test_delete_account_returns_true_and_removes_entry(self):
        self.manager.save_account("GitHub", "GitHub", "SECRET")
        result = self.manager.delete_account("GitHub")
        self.assertTrue(result)
        self.assertEqual(self.manager.load_accounts(), [])
        keyring_mock.delete_password.assert_called_with(KEYRING_SERVICE, "GitHub")

    def test_delete_nonexistent_account_returns_false(self):
        result = self.manager.delete_account("nonexistent")
        self.assertFalse(result)

    # --- get_secret ---

    def test_get_secret_calls_keyring(self):
        keyring_mock.get_password.return_value = "MYSECRET"
        result = self.manager.get_secret("GitHub")
        self.assertEqual(result, "MYSECRET")
        keyring_mock.get_password.assert_called_with(KEYRING_SERVICE, "GitHub")

    # --- remaining_seconds ---

    def test_remaining_seconds_is_between_1_and_30(self):
        remaining = self.manager.remaining_seconds()
        self.assertGreaterEqual(remaining, 1)
        self.assertLessEqual(remaining, 30)

    # --- generate_code ---

    def test_generate_code_returns_question_marks_when_no_secret(self):
        keyring_mock.get_password.return_value = None
        code = self.manager.generate_code("unknown")
        self.assertEqual(code, "??????")

    def test_generate_code_returns_6_digit_string(self):
        keyring_mock.get_password.return_value = "JBSWY3DPEHPK3PXP"
        code = self.manager.generate_code("GitHub")
        self.assertRegex(code, r'^\d{6}$')

    # --- parse_otpauth_uri ---

    def test_parse_uri_with_issuer_prefix_in_label(self):
        uri = "otpauth://totp/GitHub:user@example.com?secret=JBSWY3DPEHPK3PXP&issuer=GitHub"
        result = self.manager.parse_otpauth_uri(uri)
        self.assertEqual(result['name'], 'user@example.com')
        self.assertEqual(result['issuer'], 'GitHub')
        self.assertEqual(result['secret'], 'JBSWY3DPEHPK3PXP')

    def test_parse_uri_without_issuer_prefix(self):
        uri = "otpauth://totp/MyService?secret=JBSWY3DPEHPK3PXP"
        result = self.manager.parse_otpauth_uri(uri)
        self.assertEqual(result['name'], 'MyService')
        self.assertEqual(result['secret'], 'JBSWY3DPEHPK3PXP')

    def test_parse_uri_raises_for_non_otpauth(self):
        with self.assertRaises(ValueError):
            self.manager.parse_otpauth_uri("https://example.com")

    def test_parse_uri_raises_for_wrong_type(self):
        with self.assertRaises(ValueError):
            self.manager.parse_otpauth_uri("otpauth://hotp/Service?secret=X")

    def test_parse_uri_raises_for_missing_secret(self):
        with self.assertRaises(ValueError):
            self.manager.parse_otpauth_uri("otpauth://totp/MyService")

    # --- parse_migration_uri ---

    def test_parse_migration_uri_decodes_totp_accounts(self):
        # Build a minimal protobuf payload:
        # MigrationPayload { otp_parameters: [OtpParameters{secret, name, issuer, type=TOTP}] }
        import base64 as _b64
        secret_bytes = b'Hello!'  # raw secret
        # OtpParameters: field1=secret(bytes), field2=name(str), field3=issuer(str), field6=type(varint 2=TOTP)
        otp_param = b''
        otp_param += b'\x0a' + bytes([len(secret_bytes)]) + secret_bytes  # field 1
        otp_param += b'\x12' + bytes([len(b'user@example.com')]) + b'user@example.com'  # field 2
        otp_param += b'\x1a' + bytes([len(b'TestIssuer')]) + b'TestIssuer'  # field 3
        otp_param += b'\x30\x02'  # field 6, varint 2 (TOTP)
        # MigrationPayload: field 1 = otp_parameters
        payload = b'\x0a' + bytes([len(otp_param)]) + otp_param
        data_b64 = _b64.b64encode(payload).decode()
        uri = f"otpauth-migration://offline?data={data_b64}"

        results = self.manager.parse_migration_uri(uri)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['name'], 'user@example.com')
        self.assertEqual(results[0]['issuer'], 'TestIssuer')
        # secret should be base32 encoded
        self.assertTrue(len(results[0]['secret']) > 0)

    def test_parse_migration_uri_skips_hotp(self):
        import base64 as _b64
        secret_bytes = b'Hello!'
        # type=1 (HOTP) should be skipped
        otp_param = b'\x0a' + bytes([len(secret_bytes)]) + secret_bytes
        otp_param += b'\x12\x04test'
        otp_param += b'\x30\x01'  # HOTP
        payload = b'\x0a' + bytes([len(otp_param)]) + otp_param
        data_b64 = _b64.b64encode(payload).decode()
        uri = f"otpauth-migration://offline?data={data_b64}"

        results = self.manager.parse_migration_uri(uri)
        self.assertEqual(len(results), 0)

    def test_parse_migration_uri_raises_for_wrong_scheme(self):
        with self.assertRaises(ValueError):
            self.manager.parse_migration_uri("https://example.com")


if __name__ == '__main__':
    unittest.main()
