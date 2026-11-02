"""Phone-as-Keyboard PC server (Android USB tethering friendly).

Hosts a mobile web page that turns your phone's browser into a wireless
keyboard for this PC. No app install needed on the phone.

Usage:
    pip install -r requirements.txt
    python server.py [--host 0.0.0.0] [--port 8888] [--token SECRET]

Then open the printed URL (e.g. http://192.168.42.148:8888) in the phone's
browser while USB tethering is on.
"""

from __future__ import annotations

import argparse
import functools
import ipaddress
import json
import socket
import sys
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

BASE_DIR = Path(__file__).resolve().parent
INDEX_FILE = BASE_DIR / "index.html"

# Maps API key names -> pynput Key attribute or single character.
_SPECIAL_KEYS = {
    "enter": "enter",
    "tab": "tab",
    "esc": "esc",
    "escape": "esc",
    "backspace": "backspace",
    "delete": "delete",
    "del": "delete",
    "insert": "insert",
    "space": "space",
    "up": "up",
    "down": "down",
    "left": "left",
    "right": "right",
    "home": "home",
    "end": "end",
    "pageup": "page_up",
    "pagedown": "page_down",
    "f1": "f1",
    "f2": "f2",
    "f3": "f3",
    "f4": "f4",
    "f5": "f5",
    "f6": "f6",
    "f7": "f7",
    "f8": "f8",
    "f9": "f9",
    "f10": "f10",
    "f11": "f11",
    "f12": "f12",
    "capslock": "caps_lock",
    "printscreen": "print_screen",
    "prtsc": "print_screen",
    "pause": "pause",
    "menu": "menu",
    "context": "menu",
    "volumemute": "media_volume_mute",
    "volumeup": "media_volume_up",
    "volumedown": "media_volume_down",
    "playpause": "media_play_pause",
    "medianext": "media_next",
    "mediaprev": "media_previous",
}

_MODIFIERS = {
    "ctrl": "ctrl_l",
    "control": "ctrl_l",
    "alt": "alt_l",
    "shift": "shift_l",
    "win": "cmd_l",
    "windows": "cmd_l",
    "cmd": "cmd_l",
    "super": "cmd_l",
}


@functools.lru_cache(maxsize=1)
def _keyboard():
    """Lazily build the pynput controller so --help works without deps."""
    try:
        from pynput.keyboard import Controller, Key
    except ImportError as exc:
        raise RuntimeError(
            "Missing dependency 'pynput'. Run: pip install -r requirements.txt"
        ) from exc
    return Controller(), Key


def _resolve_key(name: str):
    """Turn an API key name into a pynput key (Key member or char)."""
    _, Key = _keyboard()
    normalized = name.strip().lower().replace("_", "").replace("-", "")
    if normalized in _MODIFIERS:
        return getattr(Key, _MODIFIERS[normalized])
    if normalized in _SPECIAL_KEYS:
        attr = _SPECIAL_KEYS[normalized]
        if not hasattr(Key, attr):
            raise ValueError(f"Key not supported on this platform: {name!r}")
        return getattr(Key, attr)
    if len(name) == 1:
        return name
    raise ValueError(f"Unknown key: {name!r}")


def type_text(text: str) -> int:
    controller, _ = _keyboard()
    if not text:
        return 0
    controller.type(text)
    return len(text)


def tap_key(key_name: str, modifiers: list[str] | None = None,
            action: str = "tap") -> None:
    controller, _ = _keyboard()
    mods = [_resolve_key(m) for m in (modifiers or [])]
    target = _resolve_key(key_name)

    if action == "down":
        for mod in mods:
            controller.press(mod)
        controller.press(target)
        return
    if action == "up":
        controller.release(target)
        for mod in reversed(mods):
            controller.release(mod)
        return
    if action != "tap":
        raise ValueError(f"Unknown action: {action!r} (want tap/down/up)")

    pressed: list = []
    try:
        for mod in mods:
            controller.press(mod)
            pressed.append(mod)
        controller.press(target)
        controller.release(target)
    finally:
        for mod in reversed(pressed):
            controller.release(mod)


def press_hotkey(keys: list[str]) -> None:
    if not keys:
        raise ValueError("hotkey needs at least one key")
    controller, _ = _keyboard()
    resolved = [_resolve_key(k) for k in keys]
    pressed: list = []
    try:
        for key in resolved:
            controller.press(key)
            pressed.append(key)
    finally:
        for key in reversed(pressed):
            try:
                controller.release(key)
            except Exception:
                pass


def local_ipv4_addresses() -> list[str]:
    """Best-effort list of this PC's IPv4 addresses (tethering first)."""
    found: list[str] = []
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None):
            ip = info[4][0]
            try:
                addr = ipaddress.ip_address(ip)
            except ValueError:
                continue
            if addr.version == 4 and not addr.is_loopback and ip not in found:
                found.append(ip)
    except socket.gaierror:
        pass
    if not found:
        # Fallback: ask the OS which source IP it would use outbound.
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                sock.connect(("8.8.8.8", 80))
                found.append(sock.getsockname()[0])
        except OSError:
            pass
    # Android USB tethering usually lives on 192.168.42.0/24; show it first.
    found.sort(key=lambda ip: (not ip.startswith("192.168.42."), ip))
    return found


class Handler(SimpleHTTPRequestHandler):
    server_version = "PhoneKeyboard/1.0"

    def __init__(self, *args, token: str | None = None, **kwargs):
        self._token = token
        super().__init__(*args, directory=str(BASE_DIR), **kwargs)

    def log_message(self, fmt: str, *args) -> None:  # quieter logs
        sys.stderr.write("  %s - %s\n" % (self.address_string(), fmt % args))

    # -- helpers ------------------------------------------------------
    def _send_json(self, payload: dict, status: int = HTTPStatus.OK) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        try:
            data = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("Body must be JSON") from exc
        if not isinstance(data, dict):
            raise ValueError("Body must be a JSON object")
        return data

    def _authorized(self) -> bool:
        if not self._token:
            return True
        if self.headers.get("X-Token") == self._token:
            return True
        query = urlparse(self.path).query
        return f"token={self._token}" in query.split("&")

    # -- routes -------------------------------------------------------
    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == "/api/ping":
            self._send_json({"ok": True})
            return
        if parsed.path in ("/", "/index.html"):
            if not INDEX_FILE.exists():
                self.send_error(
                    HTTPStatus.NOT_FOUND, "index.html missing next to server.py"
                )
                return
            self.path = "/index.html"
        return super().do_GET()

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path not in ("/api/type", "/api/key", "/api/hotkey"):
            self.send_error(HTTPStatus.NOT_FOUND, "Unknown API endpoint")
            return
        if not self._authorized():
            self._send_json({"ok": False, "error": "Invalid token"},
                            HTTPStatus.UNAUTHORIZED)
            return
        try:
            body = self._read_json()
            if parsed.path == "/api/type":
                text = body.get("text", "")
                if not isinstance(text, str):
                    raise ValueError("'text' must be a string")
                if len(text) > 2000:
                    raise ValueError("Text too long (max 2000 chars)")
                count = type_text(text)
                self._send_json({"ok": True, "typed": count})
            elif parsed.path == "/api/key":
                key = body.get("key", "")
                if not isinstance(key, str) or not key:
                    raise ValueError("'key' must be a non-empty string")
                modifiers = body.get("modifiers", [])
                if not isinstance(modifiers, list):
                    raise ValueError("'modifiers' must be a list")
                action = body.get("action", "tap")
                tap_key(key, [str(m) for m in modifiers], str(action))
                self._send_json({"ok": True})
            else:  # /api/hotkey
                keys = body.get("keys", [])
                if not isinstance(keys, list) or not keys:
                    raise ValueError("'keys' must be a non-empty list")
                press_hotkey([str(k) for k in keys])
                self._send_json({"ok": True})
        except ValueError as exc:
            self._send_json({"ok": False, "error": str(exc)},
                            HTTPStatus.BAD_REQUEST)
        except RuntimeError as exc:  # missing pynput etc.
            self._send_json({"ok": False, "error": str(exc)},
                            HTTPStatus.SERVICE_UNAVAILABLE)
        except Exception as exc:  # never leak a traceback to the phone
            self._send_json({"ok": False, "error": f"Keypress failed: {exc}"},
                            HTTPStatus.INTERNAL_SERVER_ERROR)

    def end_headers(self) -> None:
        # Phone browser talks to the PC over the tether network; allow it.
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Token")
        super().end_headers()

    def do_OPTIONS(self) -> None:  # noqa: N802 (CORS preflight)
        self.send_response(HTTPStatus.NO_CONTENT)
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Use your phone's browser as a PC keyboard over USB tethering."
    )
    parser.add_argument("--host", default="0.0.0.0",
                        help="Interface to bind (default: all, needed for tethering)")
    parser.add_argument("--port", type=int, default=8888, help="Port (default: 8888)")
    parser.add_argument("--token", default=None,
                        help="Optional secret the phone must send (X-Token header)")
    args = parser.parse_args(argv)

    handler = functools.partial(Handler, token=args.token)
    try:
        server = ThreadingHTTPServer((args.host, args.port), handler)
    except OSError as exc:
        print(f"Cannot bind {args.host}:{args.port}: {exc}", file=sys.stderr)
        return 1

    print("Phone-as-Keyboard server running.")
    print("1. On Android: connect USB, enable Settings > Network > USB tethering.")
    print("2. On this PC: allow Python through the firewall prompt if asked.")
    print("3. On the phone browser, open one of:")
    for ip in local_ipv4_addresses() or ["<this-PC-IP>"]:
        marker = "  <-- likely USB tethering" if ip.startswith("192.168.42.") else ""
        print(f"   http://{ip}:{args.port}{marker}")
    print("   (On the PC itself you can use "
          f"http://127.0.0.1:{args.port} for a quick check.)")
    if args.token:
        print("Token required: enter it on the phone page when asked.")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
