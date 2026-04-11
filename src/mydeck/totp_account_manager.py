import base64
import json
import logging
import os
import re
import time
from urllib.parse import urlparse, parse_qs, unquote

import keyring
import pyotp
import requests

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
            logging.warning("TotpAccountManager: failed to load %s: %s", self.accounts_file, e)
            return []

    def save_account(self, name: str, issuer: str, secret: str) -> None:
        accounts = self.load_accounts()
        is_new = True
        for acc in accounts:
            if acc["name"] == name:
                acc["issuer"] = issuer
                is_new = False
                break
        else:
            accounts.append({"name": name, "issuer": issuer})
        with open(self.accounts_file, "w") as f:
            json.dump(accounts, f, indent=2)
        os.chmod(self.accounts_file, 0o600)
        keyring.set_password(KEYRING_SERVICE, name, secret)
        # Auto-fetch icon for new accounts
        if is_new:
            self._auto_fetch_icon(name, issuer)

    def update_account(self, name: str, new_name: str | None = None, new_issuer: str | None = None) -> bool:
        """Update account name and/or issuer."""
        accounts = self.load_accounts()
        for acc in accounts:
            if acc["name"] == name:
                if new_issuer is not None:
                    acc["issuer"] = new_issuer
                if new_name is not None and new_name != name:
                    # Migrate keyring secret
                    secret = keyring.get_password(KEYRING_SERVICE, name)
                    if secret:
                        keyring.set_password(KEYRING_SERVICE, new_name, secret)
                        keyring.delete_password(KEYRING_SERVICE, name)
                    # Migrate image
                    if acc.get("image"):
                        old_path = acc["image"]
                        new_path = self.set_account_image(new_name, open(old_path, "rb").read()) if os.path.exists(old_path) else None
                        if new_path:
                            acc["image"] = new_path
                            os.remove(old_path)
                    acc["name"] = new_name
                with open(self.accounts_file, "w") as f:
                    json.dump(accounts, f, indent=2)
                return True
        return False

    def delete_account(self, name: str) -> bool:
        accounts = self.load_accounts()
        new_accounts = [a for a in accounts if a["name"] != name]
        if len(new_accounts) == len(accounts):
            return False
        with open(self.accounts_file, "w") as f:
            json.dump(new_accounts, f, indent=2)
        keyring.delete_password(KEYRING_SERVICE, name)
        # Remove image if exists
        img_path = self._image_path(name)
        if img_path and os.path.exists(img_path):
            os.remove(img_path)
        return True

    def set_account_image(self, name: str, image_data: bytes) -> str:
        """Save an image for an account. Returns the saved file path."""
        images_dir = os.path.join(os.path.dirname(self.accounts_file), "totp_images")
        os.makedirs(images_dir, exist_ok=True)
        # Sanitize name for filename
        safe_name = "".join(c if c.isalnum() or c in "-_." else "_" for c in name)
        path = os.path.join(images_dir, f"{safe_name}.png")
        with open(path, "wb") as f:
            f.write(image_data)
        # Store path in account data
        accounts = self.load_accounts()
        for acc in accounts:
            if acc["name"] == name:
                acc["image"] = path
                break
        with open(self.accounts_file, "w") as f:
            json.dump(accounts, f, indent=2)
        return path

    def _auto_fetch_icon(self, name: str, issuer: str) -> None:
        """Try to fetch an icon from Simple Icons (CC0 license) based on issuer/name."""
        if self._image_path(name):
            return
        for term in [issuer, name]:
            slug = self._to_simple_icons_slug(term)
            if not slug:
                continue
            try:
                url = f"https://cdn.jsdelivr.net/npm/simple-icons@latest/icons/{slug}.svg"
                resp = requests.get(url, timeout=5)
                if resp.status_code == 200:
                    # Make the SVG white for dark StreamDeck background
                    svg_content = resp.content.decode("utf-8")
                    svg_white = re.sub(
                        r'<svg([^>]*)>',
                        r'<svg\1 fill="white">',
                        svg_content,
                        count=1,
                    )
                    from cairosvg import svg2png
                    png_data = svg2png(bytestring=svg_white.encode("utf-8"),
                                       output_width=80, output_height=80)
                    self.set_account_image(name, png_data)
                    logging.info("Auto-fetched icon for %s from Simple Icons (%s)", name, slug)
                    return
            except Exception as e:
                logging.debug("Failed to fetch icon for %s (%s): %s", name, slug, e)

    @staticmethod
    def _to_simple_icons_slug(term: str) -> str:
        """Convert a service name to a Simple Icons slug."""
        if not term:
            return ""
        slug = term.lower().strip()
        slug = re.sub(r'[^a-z0-9]', '', slug)
        return slug

    def _image_path(self, name: str) -> str | None:
        accounts = self.load_accounts()
        for acc in accounts:
            if acc["name"] == name:
                return acc.get("image")
        return None

    def reorder_accounts(self, names: list[str]) -> bool:
        """Reorder accounts to match the given name list."""
        accounts = self.load_accounts()
        by_name = {a["name"]: a for a in accounts}
        reordered = []
        for name in names:
            if name in by_name:
                reordered.append(by_name.pop(name))
        # Append any remaining accounts not in the list
        for acc in accounts:
            if acc["name"] in by_name:
                reordered.append(acc)
                del by_name[acc["name"]]
        with open(self.accounts_file, "w") as f:
            json.dump(reordered, f, indent=2)
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

    def parse_migration_uri(self, uri: str) -> list[dict]:
        """Parse otpauth-migration://offline?data=... URI from Google Authenticator export.

        Returns a list of {name, issuer, secret} dicts (TOTP accounts only).
        """
        parsed = urlparse(uri)
        if parsed.scheme != "otpauth-migration":
            raise ValueError(f"Not an otpauth-migration URI: {uri}")
        params = parse_qs(parsed.query)
        data_b64 = params.get("data", [""])[0]
        if not data_b64:
            raise ValueError("Missing 'data' parameter in migration URI")
        payload = base64.b64decode(data_b64)
        return self._decode_migration_payload(payload)

    def _decode_migration_payload(self, data: bytes) -> list[dict]:
        """Decode the protobuf MigrationPayload and extract TOTP accounts."""
        results = []
        pos = 0
        while pos < len(data):
            field_num, wire_type, pos = self._read_protobuf_tag(data, pos)
            if wire_type == 2:  # length-delimited
                length, pos = self._read_varint(data, pos)
                field_data = data[pos:pos + length]
                pos += length
                if field_num == 1:  # otp_parameters
                    entry = self._decode_otp_parameters(field_data)
                    if entry is not None:
                        results.append(entry)
            elif wire_type == 0:  # varint
                _, pos = self._read_varint(data, pos)
            else:
                break
        return results

    def _decode_otp_parameters(self, data: bytes) -> dict | None:
        """Decode a single OtpParameters protobuf message."""
        secret_bytes = b""
        name = ""
        issuer = ""
        otp_type = 0
        pos = 0
        while pos < len(data):
            field_num, wire_type, pos = self._read_protobuf_tag(data, pos)
            if wire_type == 2:
                length, pos = self._read_varint(data, pos)
                field_data = data[pos:pos + length]
                pos += length
                if field_num == 1:
                    secret_bytes = field_data
                elif field_num == 2:
                    name = field_data.decode("utf-8")
                elif field_num == 3:
                    issuer = field_data.decode("utf-8")
            elif wire_type == 0:
                value, pos = self._read_varint(data, pos)
                if field_num == 6:
                    otp_type = value
            else:
                break
        # otp_type 2 = TOTP, skip HOTP (1) and unspecified (0)
        if otp_type != 2 or not secret_bytes:
            return None
        secret_b32 = base64.b32encode(secret_bytes).decode("ascii").rstrip("=")
        if ":" in name:
            name = name.split(":", 1)[1]
        if not issuer:
            issuer = name
        return {"name": name, "issuer": issuer, "secret": secret_b32}

    @staticmethod
    def _read_varint(data: bytes, pos: int) -> tuple[int, int]:
        result = 0
        shift = 0
        while pos < len(data):
            b = data[pos]
            pos += 1
            result |= (b & 0x7F) << shift
            if (b & 0x80) == 0:
                break
            shift += 7
        return result, pos

    @staticmethod
    def _read_protobuf_tag(data: bytes, pos: int) -> tuple[int, int, int]:
        tag, pos = TotpAccountManager._read_varint(data, pos)
        field_num = tag >> 3
        wire_type = tag & 0x07
        return field_num, wire_type, pos
