# Remote

A remote control for a Windows 11 PC from your iPhone (or any phone), over your home Wi‑Fi.
It's a small web page served by the PC itself: **power off, restart, a shutdown timer, volume and
monitor brightness** — no app to install on the phone.


## Demo
The following screenshots show the web application in Spanish, but the latest release is in English.
<div align="center">
  <img src="capturas/total.jpeg" width="30%" alt="Full view">
  &nbsp;&nbsp;
  <img src="capturas/temp.jpeg" width="30%" alt="Timer">
  &nbsp;&nbsp;
  <img src="capturas/brilli.jpeg" width="30%" alt="Brightness">
</div>

## Download (easiest, no setup)

Grab the ready-made app — no Python, no terminal:

**→ [Download Remote.exe](https://github.com/sergiserer/Controller/releases/latest/download/Mando.exe)**

Double‑click it. A small window opens with the address and a **QR code**: scan it with your phone
camera, open the link, and add it to your home screen. Keep the window open while you use the remote;
close it to stop.

- Only run the executable once. After that, use the shortcut **Remote - Start** 
- The first time, Windows may show a blue **"Windows protected your PC"** notice (the file isn't
  code‑signed). Click **"More info" → "Run anyway"**.
- Windows will ask about the **firewall**: choose **private networks** and allow it.
- Tick **"Start with Windows"** in the window so it's always ready (optional).
- The app creates two desktop shortcuts the first time: **Remote - Start** and **Remote - Stop**.
- Whenever you want to use it, you need to click on **Remote - Start** 

  

## Features

- **Power off** and **restart** with a 7‑second grace period and an on‑screen countdown.
- **Shutdown timer** (clock button, top left): pick hours and minutes, or a 15 min / 30 min / 1 h / 2 h
  preset, and watch the remaining time live.
- **Cancel** a pending shutdown, restart or timer.
- **Volume**: up, down (hold to repeat) and mute.
- **Monitor brightness** over DDC/CI (sun button, top right), with a slider that opens at the real value.
- When the server is off, the home‑screen app shows a **"Remote is off"** screen and reconnects by itself
  once you start it on the PC.

The countdown is handled by the server, not by Windows, so Windows never shows its full‑screen
"a shutdown has been scheduled" notice. When it reaches zero it runs `shutdown /s /f /t 0`, so **the
server must stay running** until the PC powers off.

The server uses only the Python standard library — no dependencies.

## Files

| File | What it's for |
|---|---|
| `apagar_pc.py` | The server and the web page. |
| `mando_app.py` | The desktop app: starts the server and shows the address (with a QR) in a small window. |
| `construir.ps1` | Builds `Mando.exe` from the two files above (to hand to someone with no setup). |
| `crear_accesos.ps1` | Creates the Start/Stop desktop shortcuts (for the plain‑Python setup). |
| `mando.ico` / `mando_detener.ico` | Icons for the shortcuts (the remote, and the remote with a red X). |
| `generar_icono.py` | Draws the remote icon pixel by pixel (needs Pillow). |
| `generar_iconos_windows.py` | Rebuilds the two `.ico` files from that same drawing. |
| `token.txt` | Created on first run. It's the access key. **Never committed** (it's in `.gitignore`). |

## Requirements

- Windows 10 or 11.
- Python 3.8+ with **"Add Python to PATH"** ticked (only for the plain‑Python setup; the `.exe` needs nothing).
- For brightness: a monitor with **DDC/CI** enabled in its menu (if Twinkle Tray works, it already is).
- Phone and PC on the same Wi‑Fi.

## Run it from Python (instead of the .exe)

### 1. Get the project

```powershell
cd $HOME
git clone https://github.com/sergiserer/Controller.git
cd Controller
```

### 2. Test it and get the URL

```powershell
python apagar_pc.py
```

The first run creates `token.txt` and prints a URL like:

```
http://192.168.1.50:8765/?t=XXXXXXXXXXXXXXXX
```

Open it on your phone to check it works, then close the console with `Ctrl + C`.

> Coming from another PC and want to keep the same URL on your phone? Copy the old `token.txt` into
> this folder **before** running the script.

### 3. Allow it through the firewall

Click "Allow" on the prompt Windows shows, or run PowerShell **as administrator**:

```powershell
New-NetFirewallRule -DisplayName "Remote PC" -Direction Inbound -Protocol TCP -LocalPort 8765 -Profile Private -Action Allow
```

Also check your home Wi‑Fi is set as a **Private** network
(Settings → Network & Internet → Wi‑Fi → your network → Network profile type).

### 4. Create the shortcuts

From a normal PowerShell, in the project folder:

```powershell
# Desktop only (Start and Stop)
powershell -ExecutionPolicy Bypass -File .\crear_accesos.ps1

# Desktop plus auto‑start at sign‑in
powershell -ExecutionPolicy Bypass -File .\crear_accesos.ps1 -Inicio
```

To **remove auto‑start** if you enabled it:

```powershell
Remove-Item "$([Environment]::GetFolderPath('Startup'))\Mando - Iniciar.lnk"
```

or press `Win + R`, type `shell:startup`, and delete the shortcut.

### 5. Pin the PC's IP

In your router, reserve a fixed IP for the PC (DHCP → address reservation); otherwise the URL breaks the
day the IP changes. As an alternative to an IP, you can use the PC's name: run `hostname` in a terminal
and use `http://YOUR-PC-NAME.local:8765/?t=...`.

### 6. Add it to the phone

Open the URL in the browser, tap **Share → Add to Home Screen**. It opens full screen, like an app,
with the remote icon.

## Build the .exe yourself

Every push of a version tag builds `Mando.exe` automatically on GitHub (see `.github/workflows/build.yml`)
and publishes it to **Releases**. To cut a version:

```powershell
git tag v2
git push origin v2
```

Or build it locally in one step (installs PyInstaller and qrcode for you):

```powershell
powershell -ExecutionPolicy Bypass -File .\construir.ps1
```

You'll get `Mando.exe` in the folder — the only file you need to share.

> Some antivirus tools distrust PyInstaller `.exe` files (a common false positive). If that happens,
> add an exception, or share the folder and let the person run `python mando_app.py`.

## Troubleshooting

**"Access denied" on the phone.** The URL token doesn't match `token.txt` (usually a new token was
generated). Run `python apagar_pc.py` to see the right URL, or copy the old token into `token.txt`.

**The page won't load.** Check the server is running, the phone is on the same Wi‑Fi, the firewall rule
is in place, and the network is Private.

**"The monitor does not respond over DDC/CI".** Enable DDC/CI in the monitor's own menu. Some adapters
(certain USB‑C/DisplayPort‑to‑HDMI cables and docks) don't carry DDC/CI.

**The timer didn't power off the PC.** The server stopped before reaching zero (for example, you pressed
Stop). Keep it running.

**Port 8765 is busy.** Another instance is already running — stop it first (double‑click `Liberar puerto
Mando.bat`, or close the old window), or change `PUERTO` at the top of `apagar_pc.py` and the firewall rule.

## Security

- It only works inside your local network: the router won't let in connections from the internet unless
  you open the port. **Don't open the port on the router.** To use it away from home, use a VPN like Tailscale.
- The token stops other devices on your Wi‑Fi from using it.
- Traffic is plain HTTP inside your network. To encrypt it, serve over HTTPS with an `mkcert` certificate
  or use `tailscale serve`.
- `token.txt` is in `.gitignore` — never commit it.
