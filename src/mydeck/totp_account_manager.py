import json
import os
import time
from urllib.parse import urlparse, parse_qs, unquote

import keyring
import pyotp

ACCOUNTS_FILE = os.path.expanduser("~/.config/mystreamdeck/totp_accounts.json")
KEYRING_SERVICE = "mystreamdeck-totp"


class TotpAccountManager:
    def __init__(self, accounts_file: str = ACCOUNTS_FILE):
        self.accounts_file = accounts_file
        dir_name = os.path.dirname(self.accounts_file)
        if dir_name:
            os.makedirs(dir_name, exist_ok=True)

    def load_accounts(self) -> list[dict]:
        if not os.path.exists(self.accounts_file):
            return []
        try:
            with open(self.accounts_file, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            import logging
            logging.warning("TotpAccountManager: failed to load %s: %s", self.accounts_file, e)
            return []

    def save_account(self, name: str, issuer: str, secret: str) -> None:
        accounts = self.load_accounts()
        for acc in accounts:
            if acc["name"] == name:
                acc["issuer"] = issuer
                break
        else:
            accounts.append({"name": name, "issuer": issuer})
        with open(self.accounts_file, "w") as f:
            json.dump(accounts, f, indent=2)
        os.chmod(self.accounts_file, 0o600)
        keyring.set_password(KEYRING_SERVICE, name, secret)

    def delete_account(self, name: str) -> bool:
        accounts = self.load_accounts()
        new_accounts = [a for a in accounts if a["name"] != name]
        if len(new_accounts) == len(accounts):
            return False
        with open(self.accounts_file, "w") as f:
            json.dump(new_accounts, f, indent=2)
        keyring.delete_password(KEYRING_SERVICE, name)
        return True

    def get_secret(self, name: str) -> str | None:
        return keyring.get_password(KEYRING_SERVICE, name)

    def generate_code(self, name: str) -> str:
        secret = self.get_secret(name)
        if secret is None:
            return "??????"
        return pyotp.TOTP(secret).now()

    def remaining_seconds(self) -> int:
        remaining = 30 - (int(time.time()) % 30)
        return max(1, remaining)

    def parse_otpauth_uri(self, uri: str) -> dict:
        parsed = urlparse(uri)
        if parsed.scheme != "otpauth" or parsed.netloc != "totp":
            raise ValueError(f"Invalid otpauth URI (must be otpauth://totp/...): {uri}")
        label = unquote(parsed.path.lstrip("/"))
        if ":" in label:
            issuer_from_label, account = label.split(":", 1)
        else:
            issuer_from_label, account = "", label
        params = parse_qs(parsed.query)
        secret = params.get("secret", [""])[0]
        if not secret:
            raise ValueError("Missing 'secret' parameter in otpauth URI")
        issuer = params.get("issuer", [issuer_from_label])[0] or account
        return {"name": account, "issuer": issuer, "secret": secret}
