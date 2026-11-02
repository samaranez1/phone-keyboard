# Phone as Keyboard (via USB Tethering)

> If this project helps you, consider supporting me: [ko-fi.com/samuelaranez](https://ko-fi.com/samuelaranez)

Use your Android phone's browser as a wireless keyboard for your PC — over the
USB cable, no app install needed on the phone.

How it works: you enable **USB tethering** on the phone, which creates a small
local network between phone and PC. A tiny Python server runs on the PC and
shows a keyboard page to the phone's browser. Taps on the phone become real
keystrokes on the PC.

## Setup (first time)

**1. Connect the phone to the PC with a USB cable**, then on the phone enable:

> Settings → Network & Internet → Hotspot & Tethering → **USB tethering** (ON)

(On Samsung: Settings → Connections → Mobile Hotspot and Tethering → USB tethering.)

**2. On the PC, start the server.** Either double-click `start.bat`, or:

```bat
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python server.py
```

**3. Allow the firewall prompt** if Windows asks (Python needs Private-network
access so the phone can reach it).

**4. The server prints URLs like:**

```text
http://192.168.42.148:8888  <-- likely USB tethering
```

**5. On the phone, open that URL in Chrome/Firefox** and start typing.
(The `192.168.42.x` address is the PC's address on the tether network.)

## Using the keyboard page

- **Type text** box + **Send to PC**, or enable **Live typing** so every
  keystroke is sent immediately as you type.
- **Modifiers** (Ctrl/Alt/Shift/Win) stick to the next key you tap —
  e.g. tap `Ctrl`, then tap `F5` for Ctrl+F5. They release automatically.
- **Special keys**: Esc, Tab, Backspace, Enter, arrows, Home/End, PgUp/PgDn…
- **Shortcuts**: Copy/Paste/Undo/Save, Alt+Tab, Win+D, Task Manager, etc.
- **Media**: volume, mute, play/pause.
- `Ctrl+Enter` inside the text box sends the text.

## Options

```bat
python server.py --port 8888            :: change port
python server.py --token mysecret123    :: require a secret (enter it on the phone page)
```

## Troubleshooting

| Symptom | Fix |
|---|---|
| Phone browser can't reach the page | Check USB tethering is ON; the cable must be data-capable. Re-open the exact URL the server printed. |
| `192.168.42.x` URL missing | On the PC run `ipconfig` and look for a `192.168.42.*` adapter ("Remote NDIS"). If absent, toggle USB tethering off/on and reconnect the cable. |
| Windows firewall blocks it | Allow Python on Private networks, or run `server.py` again and click **Allow access**. |
| Keys do nothing / error about pynput | Run `pip install -r requirements.txt` inside `.venv`. Some games with anti-cheat block synthetic keys. |
| Page says Disconnected | The server stopped or the phone lost the tether network. Restart the server, reload the page. |
| Wrong characters for your layout | Key names follow the PC's layout; plain text typing follows what you typed. |

## Files

- `server.py` — PC server: serves the page, emulates keystrokes (via `pynput`).
- `index.html` — the phone keyboard page (fully offline, no CDN needed).
- `requirements.txt`, `start.bat` — install + launch helpers.

## Security note

Anyone who can reach the server URL can type on your PC. USB tethering only
exposes it to your phone, but on shared/public networks use `--token` and stop
the server when done.

---
*This project was built with Muse Code, an agentic coding assistant.*
