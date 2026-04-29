import json
import logging


class TotpEndpointsMixin:
    """TOTP-related endpoint handlers for DeckOutputWebHandler.

    Provides the `res_totp_*` methods. Designed to be mixed into a class
    that also inherits from `http.server.BaseHTTPRequestHandler`, since
    these methods rely on `self.headers`, `self.rfile`, and the
    `self.api_json_response()` helper defined on the handler.
    """

    def res_totp_accounts(self):
        from .totp_account_manager import TotpAccountManager
        manager = TotpAccountManager()
        return self.api_json_response(manager.load_accounts())

    def res_totp_scan(self):
        """Decode QR code from base64 image and return the raw URI (no registration)."""
        import base64
        from io import BytesIO
        from PIL import Image as PILImage
        from pyzbar.pyzbar import decode as pyzbar_decode

        try:
            content_length = int(self.headers['content-length'])
            if content_length > 10 * 1024 * 1024:
                return self.api_json_response({"error": "image too large"})
            body = json.loads(self.rfile.read(content_length).decode('utf-8'))
            image_data = base64.b64decode(body['image_b64'])
            im = PILImage.open(BytesIO(image_data)).convert('L')  # grayscale for better detection
            logging.debug("TOTP scan: image size=%s, mode=%s", im.size, im.mode)
            decoded = pyzbar_decode(im)
            logging.debug("TOTP scan: pyzbar found %d codes", len(decoded))
            if not decoded:
                return self.api_json_response({})
            uri = decoded[0].data.decode('utf-8')
            logging.debug("TOTP scan: decoded URI=%s", uri[:50])
            return self.api_json_response({"uri": uri})
        except Exception as e:
            logging.error("TOTP scan error: %s", e)
            return self.api_json_response({"error": str(e)})

    def res_totp_upload(self):
        import base64
        from io import BytesIO
        from PIL import Image as PILImage
        from pyzbar.pyzbar import decode as pyzbar_decode
        from .totp_account_manager import TotpAccountManager

        try:
            content_length = int(self.headers['content-length'])
            if content_length > 10 * 1024 * 1024:
                return self.api_json_response({"error": "image too large (max 10 MB)"})
            body = json.loads(self.rfile.read(content_length).decode('utf-8'))
            image_data = base64.b64decode(body['image_b64'])
            im = PILImage.open(BytesIO(image_data))
            decoded = pyzbar_decode(im)
            if not decoded:
                return self.api_json_response({"error": "QR code not found in image"})
            uri = decoded[0].data.decode('utf-8')
            manager = TotpAccountManager()
            parsed = manager.parse_otpauth_uri(uri)
            name = body.get('name') or parsed['name']
            manager.save_account(name, parsed['issuer'], parsed['secret'])
            return self.api_json_response({"ok": True, "name": name})
        except Exception as e:
            logging.error("TOTP upload error: %s", e)
            return self.api_json_response({"error": str(e)})

    def res_totp_register(self):
        import base64 as _base64
        from .totp_account_manager import TotpAccountManager

        try:
            content_length = int(self.headers['content-length'])
            body = json.loads(self.rfile.read(content_length).decode('utf-8'))
            manager = TotpAccountManager()
            uri = body.get('uri', '')
            if uri.startswith('otpauth-migration://'):
                entries = manager.parse_migration_uri(uri)
                if not entries:
                    return self.api_json_response({"error": "No TOTP accounts found in migration data"})
                names = []
                for entry in entries:
                    manager.save_account(entry['name'], entry['issuer'], entry['secret'])
                    names.append(entry['name'])
                return self.api_json_response({"ok": True, "name": ", ".join(names), "count": len(names)})
            elif uri:
                parsed = manager.parse_otpauth_uri(uri)
                name = body.get('name') or parsed['name']
                manager.save_account(name, parsed['issuer'], parsed['secret'])
            else:
                name = body['name']
                issuer = body.get('issuer', name)
                secret = body['secret'].upper().replace(' ', '')
                try:
                    _base64.b32decode(secret, casefold=True)
                except Exception:
                    return self.api_json_response({"error": "invalid Base32 secret"})
                manager.save_account(name, issuer, secret)
            return self.api_json_response({"ok": True, "name": name})
        except Exception as e:
            logging.error("TOTP register error: %s", e)
            return self.api_json_response({"error": str(e)})

    def res_totp_set_image(self):
        import base64
        import requests as req
        from .totp_account_manager import TotpAccountManager

        try:
            content_length = int(self.headers['content-length'])
            if content_length > 10 * 1024 * 1024:
                return self.api_json_response({"error": "image too large (max 10 MB)"})
            body = json.loads(self.rfile.read(content_length).decode('utf-8'))
            name = body['name']
            manager = TotpAccountManager()
            if 'image_url' in body:
                resp = req.get(body['image_url'], timeout=10)
                if resp.status_code != 200:
                    return self.api_json_response({"error": f"画像の取得に失敗: HTTP {resp.status_code}"})
                image_data = resp.content
            else:
                image_data = base64.b64decode(body['image_b64'])
            path = manager.set_account_image(name, image_data)
            return self.api_json_response({"ok": True, "path": path})
        except Exception as e:
            logging.error("TOTP set_image error: %s", e)
            return self.api_json_response({"error": str(e)})

    def res_totp_delete(self):
        from .totp_account_manager import TotpAccountManager

        try:
            content_length = int(self.headers['content-length'])
            body = json.loads(self.rfile.read(content_length).decode('utf-8'))
            name = body['name']
            manager = TotpAccountManager()
            ok = manager.delete_account(name)
            return self.api_json_response({"ok": ok})
        except Exception as e:
            logging.error("TOTP delete error: %s", e)
            return self.api_json_response({"error": str(e)})

    def res_totp_reorder(self):
        from .totp_account_manager import TotpAccountManager

        try:
            content_length = int(self.headers['content-length'])
            body = json.loads(self.rfile.read(content_length).decode('utf-8'))
            names = body['names']
            manager = TotpAccountManager()
            ok = manager.reorder_accounts(names)
            return self.api_json_response({"ok": ok})
        except Exception as e:
            logging.error("TOTP reorder error: %s", e)
            return self.api_json_response({"error": str(e)})

    def res_totp_fetch_icon(self):
        from .totp_account_manager import TotpAccountManager

        try:
            content_length = int(self.headers['content-length'])
            body = json.loads(self.rfile.read(content_length).decode('utf-8'))
            name = body['name']
            manager = TotpAccountManager()
            accounts = manager.load_accounts()
            issuer = name
            for acc in accounts:
                if acc["name"] == name:
                    issuer = acc.get("issuer", name)
                    # Clear existing image so _auto_fetch_icon will run
                    if acc.get("image"):
                        acc.pop("image")
                        with open(manager.accounts_file, "w") as f:
                            json.dump(accounts, f, indent=2)
                    break
            manager._auto_fetch_icon(name, issuer)
            # Check if it worked
            path = manager._image_path(name)
            if path:
                return self.api_json_response({"ok": True, "path": path})
            else:
                return self.api_json_response({"error": "アイコンが見つかりませんでした"})
        except Exception as e:
            logging.error("TOTP fetch_icon error: %s", e)
            return self.api_json_response({"error": str(e)})

    def res_totp_update(self):
        from .totp_account_manager import TotpAccountManager

        try:
            content_length = int(self.headers['content-length'])
            body = json.loads(self.rfile.read(content_length).decode('utf-8'))
            name = body['name']
            new_name = body.get('new_name')
            new_issuer = body.get('new_issuer')
            manager = TotpAccountManager()
            ok = manager.update_account(name, new_name=new_name, new_issuer=new_issuer)
            return self.api_json_response({"ok": ok})
        except Exception as e:
            logging.error("TOTP update error: %s", e)
            return self.api_json_response({"error": str(e)})
