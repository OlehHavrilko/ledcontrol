# ELK-BLEDOM LED Strip Controller (Windows Desktop)

[![Windows build](https://github.com/OlehHavrilko/ledcontrol/actions/workflows/windows-build.yml/badge.svg)](https://github.com/OlehHavrilko/ledcontrol/actions/workflows/windows-build.yml)
[![Latest release](https://img.shields.io/github/v/release/OlehHavrilko/ledcontrol)](https://github.com/OlehHavrilko/ledcontrol/releases/latest)
[![Downloads](https://img.shields.io/github/downloads/OlehHavrilko/ledcontrol/total)](https://github.com/OlehHavrilko/ledcontrol/releases)

Modern desktop app (Python + CustomTkinter) to control ELK-BLEDOM BLE RGB LED strips using the common 9-byte ELK-BLEDOM protocol frames.

## Install

```bash
python -m venv .venv
.venv\\Scripts\\activate
pip install -r requirements.txt
```

## Run

```bash
python main.py
```

The app will scan for devices whose name contains `ELK-BLEDOM`. It saves `config.json` on first run and auto-reconnects to the last device when possible.

## Config

`config.json` (auto-created) now also supports:

```json
{
  "auto_reconnect": true,
  "write_delay_ms": 50,
  "default_power_on": true,
  "http_api": { "enabled": false, "host": "127.0.0.1", "port": 8787 }
}
```

## HTTP API (optional)

Enable `http_api.enabled=true` in `config.json`, restart the app, then use:

- `POST /color?r=255&g=0&b=0`
- `POST /power?on=true`
- `POST /brightness?pct=80`
- `POST /effect?mode=3&speed=120`

## Build native Windows `.exe` + installer

### 1) Build the app folder (PyInstaller)

In PowerShell on Windows:

```powershell
.\tools\windows\build.ps1
```

Output:
- `dist\elk-bledom-controller\elk-bledom-controller.exe`

### 2) Build a normal installer (Inno Setup)

1. Install Inno Setup.
2. Open `tools\windows\installer.iss` and click **Compile** (or run `ISCC.exe` on it).

Output:
- `dist-installer\elk-bledom-controller-setup.exe`

## Windows BLE notes

- Windows 10 (1803+) / Windows 11 recommended.
- You need a Bluetooth adapter with BLE support.
- If connecting/scanning fails with access/permission errors, check Windows Bluetooth permissions and ensure Bluetooth is enabled.
