from __future__ import annotations

import asyncio
import re
import tkinter as tk
from typing import Any

import customtkinter as ctk

from .ble_controller import BleController, ConnectionState, NAME_SUBSTR, WRITE_UUID_DEFAULT
from .config import AppConfig
from .api import ApiConfig, start_api_in_thread
from .service import LedService, LedState


EFFECTS: list[tuple[int, str]] = [
    (0x00, "Static"),
    (0x01, "Jump (RGB)"),
    (0x02, "Jump (RGBYCMW)"),
    (0x03, "Crossfade (RGB)"),
    (0x04, "Crossfade (RGBYCMW)"),
    (0x05, "Blink (RGB)"),
    (0x06, "Blink (RGBYCMW)"),
    (0x07, "Breath (RGB)"),
    (0x08, "Breath (RGBYCMW)"),
    (0x09, "Strobe (RGB)"),
    (0x0A, "Strobe (RGBYCMW)"),
    (0x0B, "Chase"),
    (0x0C, "Sparkle"),
    (0x0D, "Wave"),
    (0x0E, "Rainbow"),
    (0x0F, "Rainbow (Slow)"),
    (0x10, "Rainbow (Fast)"),
    (0x11, "Police"),
    (0x12, "Fire"),
    (0x13, "Ice"),
    (0x14, "Forest"),
    (0x15, "Ocean"),
    (0x16, "Party"),
    (0x17, "Random"),
]


PALETTE: list[tuple[str, tuple[int, int, int]]] = [
    ("Red", (255, 0, 0)),
    ("Green", (0, 255, 0)),
    ("Blue", (0, 0, 255)),
    ("White", (255, 255, 255)),
    ("Warm", (255, 160, 70)),
    ("Cyan", (0, 255, 255)),
    ("Magenta", (255, 0, 255)),
    ("Yellow", (255, 255, 0)),
]


HEX_RE = re.compile(r"^#?[0-9a-fA-F]{6}$")


class LedControllerApp(ctk.CTk):
    def __init__(self, config_path: str = "config.json") -> None:
        super().__init__()
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.title("ELK-BLEDOM LED Controller")
        self.geometry("600x700")
        self.resizable(False, False)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self.cfg = AppConfig.load(config_path)

        self._ble = BleController(
            on_state=self._on_ble_state_from_thread,
            on_last_command=self._on_last_command_from_thread,
            on_log=self._on_log_from_thread,
        )
        self._ble.start()
        self._ble.set_write_delay_ms(int(self.cfg.data.get("write_delay_ms", 50)))

        self._connected = False
        self._power_on = bool(self.cfg.data.get("default_power_on", True))
        self._device_label = ""
        self._rssi_label = ""
        self._last_command = ""
        self._logs: list[str] = []
        self._color_debounce: str | None = None
        self._brightness_debounce: str | None = None

        last_color = self.cfg.data.get("last_color", [255, 100, 0])
        self._service = LedService(
            self._ble,
            LedState(
                power_on=self._power_on,
                r=int(last_color[0]),
                g=int(last_color[1]),
                b=int(last_color[2]),
                brightness_pct=int(self.cfg.data.get("last_brightness", 80)),
            ),
        )
        self._api_thread = None

        self._build_ui()
        self._bind_shortcuts()

        self.after(200, self._startup_autoreconnect)
        self._maybe_start_api()

    def _maybe_start_api(self) -> None:
        http = self.cfg.data.get("http_api", {}) or {}
        if not bool(http.get("enabled", False)):
            return
        host = str(http.get("host") or "127.0.0.1")
        port = int(http.get("port") or 8787)
        self._api_thread = start_api_in_thread(self._service, ApiConfig(host=host, port=port))
        self._append_log(f"HTTP API started on http://{host}:{port}")

    def _bind_shortcuts(self) -> None:
        self.bind("<space>", lambda _e: self._toggle_power())
        self.bind("<Up>", lambda _e: self._bump_brightness(+5))
        self.bind("<Down>", lambda _e: self._bump_brightness(-5))
        self.bind("<Left>", lambda _e: self._bump_speed(-10))
        self.bind("<Right>", lambda _e: self._bump_speed(+10))
        for i, (_name, rgb) in enumerate(PALETTE, start=1):
            self.bind(f"<Control-Key-{i}>", lambda _e, c=rgb: self._set_color(*c))

    def _build_ui(self) -> None:
        self.grid_columnconfigure(0, weight=1)

        header = ctk.CTkFrame(self, corner_radius=12)
        header.grid(row=0, column=0, padx=16, pady=(16, 10), sticky="ew")
        header.grid_columnconfigure(0, weight=1)

        title = ctk.CTkLabel(header, text="ELK-BLEDOM Controller", font=("Segoe UI", 20, "bold"))
        title.grid(row=0, column=0, sticky="w", padx=14, pady=(12, 4))

        subtitle = ctk.CTkLabel(
            header,
            text=f"Scan/connect to BLE devices named like “{NAME_SUBSTR}”",
            text_color=("gray70", "gray70"),
        )
        subtitle.grid(row=1, column=0, sticky="w", padx=14, pady=(0, 12))

        self._device_frame = ctk.CTkFrame(self, corner_radius=12)
        self._device_frame.grid(row=1, column=0, padx=16, pady=(0, 10), sticky="ew")
        self._device_frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(self._device_frame, text="Device").grid(row=0, column=0, padx=14, pady=12, sticky="w")
        self._device_var = tk.StringVar(value="(scan to populate)")
        self._device_menu = ctk.CTkOptionMenu(self._device_frame, variable=self._device_var, values=["(scan)"])
        self._device_menu.grid(row=0, column=1, padx=10, pady=12, sticky="ew")

        self._scan_btn = ctk.CTkButton(self._device_frame, text="Scan", command=self._scan_devices)
        self._scan_btn.grid(row=0, column=2, padx=(10, 14), pady=12)

        self._connect_btn = ctk.CTkButton(self._device_frame, text="Connect", command=self._connect_or_disconnect)
        self._connect_btn.grid(row=1, column=2, padx=(10, 14), pady=(0, 12))

        ctk.CTkLabel(self._device_frame, text="Write UUID").grid(
            row=1, column=0, padx=14, pady=(0, 12), sticky="w"
        )
        self._uuid_var = tk.StringVar(
            value=self.cfg.data.get("last_device", {}).get("write_uuid", WRITE_UUID_DEFAULT)
        )
        self._uuid_entry = ctk.CTkEntry(self._device_frame, textvariable=self._uuid_var)
        self._uuid_entry.grid(row=1, column=1, padx=10, pady=(0, 12), sticky="ew")

        self._power_frame = ctk.CTkFrame(self, corner_radius=12)
        self._power_frame.grid(row=2, column=0, padx=16, pady=(0, 10), sticky="ew")
        self._power_frame.grid_columnconfigure(0, weight=1)
        self._power_btn = ctk.CTkButton(
            self._power_frame, text="POWER ON" if self._power_on else "POWER OFF", height=46, command=self._toggle_power
        )
        self._power_btn.grid(row=0, column=0, padx=14, pady=14, sticky="ew")

        self._color_frame = ctk.CTkFrame(self, corner_radius=12)
        self._color_frame.grid(row=3, column=0, padx=16, pady=(0, 10), sticky="ew")
        self._color_frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(self._color_frame, text="Color").grid(row=0, column=0, padx=14, pady=(12, 6), sticky="w")
        self._preview = tk.Canvas(self._color_frame, width=44, height=18, highlightthickness=0)
        self._preview.grid(row=0, column=1, padx=10, pady=(12, 6), sticky="w")
        self._preview_rect = self._preview.create_rectangle(0, 0, 44, 18, outline="", fill="#ff6400")

        # Intentionally no modal color wheel here: sliders + HEX provide non-blocking "live" UX.

        self._r_var = tk.IntVar(value=int(self.cfg.data.get("last_color", [255, 100, 0])[0]))
        self._g_var = tk.IntVar(value=int(self.cfg.data.get("last_color", [255, 100, 0])[1]))
        self._b_var = tk.IntVar(value=int(self.cfg.data.get("last_color", [255, 100, 0])[2]))
        self._hex_var = tk.StringVar(value=self._rgb_to_hex(self._r_var.get(), self._g_var.get(), self._b_var.get()))

        self._add_rgb_row("R", 1, self._r_var, "red")
        self._add_rgb_row("G", 2, self._g_var, "green")
        self._add_rgb_row("B", 3, self._b_var, "blue")

        ctk.CTkLabel(self._color_frame, text="HEX").grid(row=4, column=0, padx=14, pady=(4, 12), sticky="w")
        self._hex_entry = ctk.CTkEntry(self._color_frame, textvariable=self._hex_var)
        self._hex_entry.grid(row=4, column=1, padx=10, pady=(4, 12), sticky="ew")
        self._hex_entry.bind("<Return>", lambda _e: self._apply_hex())
        self._hex_apply_btn = ctk.CTkButton(self._color_frame, text="Apply", width=90, command=self._apply_hex)
        self._hex_apply_btn.grid(row=4, column=2, padx=(10, 14), pady=(4, 12))

        palette_frame = ctk.CTkFrame(self, corner_radius=12)
        palette_frame.grid(row=4, column=0, padx=16, pady=(0, 10), sticky="ew")
        palette_frame.grid_columnconfigure(tuple(range(8)), weight=1)
        ctk.CTkLabel(palette_frame, text="Palette").grid(
            row=0, column=0, padx=14, pady=(10, 6), sticky="w", columnspan=8
        )
        for i, (name, rgb) in enumerate(PALETTE):
            btn = ctk.CTkButton(palette_frame, text=name, command=lambda c=rgb: self._set_color(*c))
            btn.grid(row=1, column=i, padx=6, pady=(0, 12), sticky="ew")

        self._recent_frame = ctk.CTkFrame(self, corner_radius=12)
        self._recent_frame.grid(row=5, column=0, padx=16, pady=(0, 10), sticky="ew")
        self._recent_frame.grid_columnconfigure(tuple(range(8)), weight=1)
        ctk.CTkLabel(self._recent_frame, text="Recent").grid(
            row=0, column=0, padx=14, pady=(10, 6), sticky="w", columnspan=8
        )
        self._recent_buttons: list[ctk.CTkButton] = []
        for i in range(8):
            btn = ctk.CTkButton(self._recent_frame, text="—", command=lambda: None)
            btn.grid(row=1, column=i, padx=6, pady=(0, 12), sticky="ew")
            self._recent_buttons.append(btn)
        self._render_recent_colors()

        self._bright_frame = ctk.CTkFrame(self, corner_radius=12)
        self._bright_frame.grid(row=6, column=0, padx=16, pady=(0, 10), sticky="ew")
        self._bright_frame.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(self._bright_frame, text="Brightness").grid(row=0, column=0, padx=14, pady=12, sticky="w")
        self._brightness_var = tk.IntVar(value=int(self.cfg.data.get("last_brightness", 80)))
        self._brightness_label = ctk.CTkLabel(self._bright_frame, text=f"{self._brightness_var.get()}%")
        self._brightness_label.grid(row=0, column=2, padx=(10, 14), pady=12, sticky="e")
        self._brightness_slider = ctk.CTkSlider(
            self._bright_frame, from_=0, to=100, number_of_steps=100, command=self._on_brightness_slider
        )
        self._brightness_slider.set(self._brightness_var.get())
        self._brightness_slider.grid(row=0, column=1, padx=10, pady=12, sticky="ew")

        self._effects_frame = ctk.CTkFrame(self, corner_radius=12)
        self._effects_frame.grid(row=7, column=0, padx=16, pady=(0, 10), sticky="ew")
        self._effects_frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(self._effects_frame, text="Effects").grid(row=0, column=0, padx=14, pady=(12, 6), sticky="w")
        self._effect_map = {name: mode for mode, name in EFFECTS}
        effect_values = [name for _mode, name in EFFECTS]
        self._effect_var = tk.StringVar(value=effect_values[0])

        grid = ctk.CTkFrame(self._effects_frame, corner_radius=10)
        grid.grid(row=1, column=0, padx=14, pady=(0, 8), sticky="ew")
        for c in range(6):
            grid.grid_columnconfigure(c, weight=1)
        for i, (mode, name) in enumerate(EFFECTS):
            r = i // 6
            c = i % 6
            btn = ctk.CTkButton(
                grid,
                text=name.split(" ")[0],
                width=90,
                height=28,
                command=lambda m=mode, n=name: self._apply_effect(mode=m, name=n),
            )
            btn.grid(row=r, column=c, padx=4, pady=4, sticky="ew")

        ctk.CTkLabel(self._effects_frame, text="Speed").grid(row=2, column=0, padx=14, pady=(0, 12), sticky="w")
        self._speed_var = tk.IntVar(value=120)
        self._speed_slider = ctk.CTkSlider(
            self._effects_frame, from_=0, to=255, number_of_steps=255, command=self._on_speed_slider
        )
        self._speed_slider.set(self._speed_var.get())
        self._speed_slider.grid(row=2, column=0, padx=(90, 90), pady=(0, 12), sticky="ew")
        self._speed_label = ctk.CTkLabel(self._effects_frame, text=str(self._speed_var.get()))
        self._speed_label.grid(row=2, column=0, padx=(14, 14), pady=(0, 12), sticky="e")

        hint = ctk.CTkLabel(self._effects_frame, text="Tip: click an effect button to apply.", text_color=("gray70", "gray70"))
        hint.grid(row=3, column=0, padx=14, pady=(0, 14), sticky="w")

        self._scenes_frame = ctk.CTkFrame(self, corner_radius=12)
        self._scenes_frame.grid(row=8, column=0, padx=16, pady=(0, 10), sticky="ew")
        self._scenes_frame.grid_columnconfigure(0, weight=1)

        top = ctk.CTkFrame(self._scenes_frame, fg_color="transparent")
        top.grid(row=0, column=0, padx=14, pady=(12, 8), sticky="ew")
        top.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(top, text="Scenes").grid(row=0, column=0, sticky="w")
        self._scene_name_var = tk.StringVar(value="")
        self._scene_name_entry = ctk.CTkEntry(top, textvariable=self._scene_name_var, placeholder_text="Scene name")
        self._scene_name_entry.grid(row=0, column=1, padx=10, sticky="ew")
        self._scene_save_btn = ctk.CTkButton(top, text="Save", width=90, command=self._save_scene)
        self._scene_save_btn.grid(row=0, column=2, sticky="e")

        self._scene_list = ctk.CTkScrollableFrame(self._scenes_frame, corner_radius=10, height=120)
        self._scene_list.grid(row=1, column=0, padx=14, pady=(0, 14), sticky="ew")
        self._render_scenes()

        self._debug_frame = ctk.CTkFrame(self, corner_radius=12)
        self._debug_frame.grid(row=9, column=0, padx=16, pady=(0, 10), sticky="ew")
        self._debug_frame.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(self._debug_frame, text="Debug").grid(row=0, column=0, padx=14, pady=(10, 6), sticky="w")
        self._debug_text = ctk.CTkTextbox(self._debug_frame, height=90)
        self._debug_text.grid(row=1, column=0, padx=14, pady=(0, 12), sticky="ew")
        self._debug_text.configure(state="disabled")

        self._status = ctk.CTkFrame(self, corner_radius=0)
        self._status.grid(row=10, column=0, padx=0, pady=(0, 0), sticky="ew")
        self._status.grid_columnconfigure(2, weight=1)

        self._dot = ctk.CTkLabel(self._status, text="●", text_color="red", font=("Segoe UI", 14, "bold"))
        self._dot.grid(row=0, column=0, padx=(12, 6), pady=10, sticky="w")
        self._status_label = ctk.CTkLabel(self._status, text="Disconnected")
        self._status_label.grid(row=0, column=1, padx=(0, 10), pady=10, sticky="w")
        self._device_status = ctk.CTkLabel(self._status, text="", text_color=("gray70", "gray70"))
        self._device_status.grid(row=0, column=2, padx=10, pady=10, sticky="w")
        self._cmd_status = ctk.CTkLabel(self._status, text="", text_color=("gray70", "gray70"))
        self._cmd_status.grid(row=0, column=3, padx=(0, 12), pady=10, sticky="e")

        self._sync_preview()
        self._refresh_status_bar()

    def _add_rgb_row(self, label: str, row: int, var: tk.IntVar, _accent: str) -> None:
        ctk.CTkLabel(self._color_frame, text=label).grid(row=row, column=0, padx=14, pady=4, sticky="w")

        slider = ctk.CTkSlider(
            self._color_frame, from_=0, to=255, number_of_steps=255, command=lambda _v: self._on_rgb_slider()
        )
        slider.set(var.get())
        slider.grid(row=row, column=1, padx=10, pady=4, sticky="ew")

        entry_var = tk.StringVar(value=str(var.get()))
        entry = ctk.CTkEntry(self._color_frame, textvariable=entry_var, width=90)
        entry.grid(row=row, column=2, padx=(10, 14), pady=4, sticky="e")

        def sync_from_entry() -> None:
            try:
                v = int(entry_var.get().strip())
            except ValueError:
                entry_var.set(str(var.get()))
                return
            v = max(0, min(255, v))
            var.set(v)
            slider.set(v)
            entry_var.set(str(v))
            self._on_rgb_slider()

        def sync_from_var(*_a: Any) -> None:
            entry_var.set(str(var.get()))
            slider.set(var.get())

        entry.bind("<Return>", lambda _e: sync_from_entry())
        var.trace_add("write", sync_from_var)

        setattr(self, f"_slider_{label.lower()}", slider)

    def _startup_autoreconnect(self) -> None:
        if not bool(self.cfg.data.get("auto_reconnect", True)):
            self._scan_devices()
            return
        last = self.cfg.data.get("last_device", {}) or {}
        addr = (last.get("address") or "").strip()
        name = (last.get("name") or "").strip()
        write_uuid = (last.get("write_uuid") or WRITE_UUID_DEFAULT).strip()
        if not addr:
            self._scan_devices()
            return
        self._uuid_var.set(write_uuid)
        self._toast(f"Auto-connecting to {name or addr}…")
        self._connect(address=addr, name=name, write_uuid=write_uuid)

    def _scan_devices(self) -> None:
        self._scan_btn.configure(state="disabled")
        self._device_menu.configure(values=["Scanning…"])
        self._device_var.set("Scanning…")

        async def do_scan() -> list[Any]:
            return await self._ble.scan(timeout=5.0)

        fut = self._ble.submit(do_scan())

        def done() -> None:
            self._scan_btn.configure(state="normal")
            try:
                results = fut.result()
            except Exception as e:
                self._toast(f"Scan failed: {e}")
                self._device_menu.configure(values=["(scan)"])
                self._device_var.set("(scan)")
                return
            if not results:
                self._device_menu.configure(values=["(none found)"])
                self._device_var.set("(none found)")
                return
            values = [f"{d.name}  ({d.address})  RSSI {d.rssi}" for d in results]
            self._scan_results = results  # list[DeviceInfo]
            self._device_menu.configure(values=values)
            self._device_var.set(values[0])

        self.after(50, lambda: self._poll_future(fut, done))

    def _connect_or_disconnect(self) -> None:
        if self._connected:
            self._disconnect()
            return
        if not hasattr(self, "_scan_results"):
            self._scan_devices()
            return
        choice = self._device_var.get()
        match = re.search(r"\(([0-9A-Fa-f:]{17})\)", choice)
        if not match:
            self._toast("Pick a device (scan first)")
            return
        address = match.group(1)
        name = choice.split("(")[0].strip()
        raw = None
        for d in getattr(self, "_scan_results", []) or []:
            if getattr(d, "address", None) == address:
                raw = getattr(d, "raw", None)
                break
        self._connect(
            address=address,
            name=name,
            write_uuid=self._uuid_var.get().strip() or WRITE_UUID_DEFAULT,
            raw_device=raw,
        )

    def _connect(self, address: str, name: str, write_uuid: str, raw_device: Any | None = None) -> None:
        self._connect_btn.configure(state="disabled", text="Connecting…")
        self._uuid_entry.configure(state="disabled")

        async def do_connect() -> None:
            await self._ble.connect(address=address, name=name, write_uuid=write_uuid, raw_device=raw_device)
            self._ble.set_last_device(address=address, name=name, write_uuid=write_uuid)

        fut = self._ble.submit(do_connect())

        def done() -> None:
            self._connect_btn.configure(state="normal")
            self._uuid_entry.configure(state="normal")
            try:
                fut.result()
            except Exception as e:
                self._connect_btn.configure(text="Connect")
                self._toast(f"Connect failed: {self._friendly_ble_error(e)}")
                return
            self.cfg.data["last_device"] = {"address": address, "name": name, "write_uuid": write_uuid}
            self.cfg.save()
            self._toast("Connected")
            if bool(self.cfg.data.get("default_power_on", True)) and self._power_on:
                self._service.set_power(True)

        self.after(50, lambda: self._poll_future(fut, done))

    def _disconnect(self) -> None:
        self._connect_btn.configure(state="disabled", text="Disconnecting…")

        async def do_disconnect() -> None:
            await self._ble.disconnect()

        fut = self._ble.submit(do_disconnect())

        def done() -> None:
            self._connect_btn.configure(state="normal", text="Connect")
            try:
                fut.result()
            except Exception as e:
                self._toast(f"Disconnect error: {e}")

        self.after(50, lambda: self._poll_future(fut, done))

    def _toggle_power(self) -> None:
        self._power_on = not self._power_on
        self._power_btn.configure(text="POWER ON" if self._power_on else "POWER OFF")
        if self._connected:
            self._service.set_power(self._power_on)

    def _apply_hex(self) -> None:
        text = self._hex_var.get().strip()
        if not HEX_RE.match(text):
            self._toast("Invalid HEX (use #RRGGBB)")
            return
        if not text.startswith("#"):
            text = "#" + text
            self._hex_var.set(text)
        r = int(text[1:3], 16)
        g = int(text[3:5], 16)
        b = int(text[5:7], 16)
        self._set_color(r, g, b, remember=True, send=True)

    def _on_rgb_slider(self) -> None:
        self._hex_var.set(self._rgb_to_hex(self._r_var.get(), self._g_var.get(), self._b_var.get()))
        self._sync_preview()
        self._debounced_send_color()

    def _set_color(self, r: int, g: int, b: int, *, remember: bool = True, send: bool = True) -> None:
        r = max(0, min(255, int(r)))
        g = max(0, min(255, int(g)))
        b = max(0, min(255, int(b)))
        self._r_var.set(r)
        self._g_var.set(g)
        self._b_var.set(b)
        self._hex_var.set(self._rgb_to_hex(r, g, b))
        self._sync_preview()
        if remember:
            self._push_recent_color([r, g, b])
            self.cfg.data["last_color"] = [r, g, b]
            self.cfg.save()
        if send:
            self._debounced_send_color()

    def _debounced_send_color(self) -> None:
        if self._color_debounce:
            self.after_cancel(self._color_debounce)
        self._color_debounce = self.after(120, self._send_color_now)

    def _send_color_now(self) -> None:
        self._color_debounce = None
        r, g, b = self._r_var.get(), self._g_var.get(), self._b_var.get()
        self.cfg.data["last_color"] = [r, g, b]
        self.cfg.save()
        if self._connected:
            self._service.set_color(r, g, b)

    def _on_brightness_slider(self, value: float) -> None:
        pct = int(round(value))
        self._brightness_var.set(pct)
        self._brightness_label.configure(text=f"{pct}%")
        if self._brightness_debounce:
            self.after_cancel(self._brightness_debounce)
        self._brightness_debounce = self.after(120, self._send_brightness_now)

    def _send_brightness_now(self) -> None:
        self._brightness_debounce = None
        pct = int(self._brightness_var.get())
        self.cfg.data["last_brightness"] = pct
        self.cfg.save()
        if self._connected:
            self._service.set_brightness_pct(pct)

    def _on_speed_slider(self, value: float) -> None:
        v = int(round(value))
        self._speed_var.set(v)
        self._speed_label.configure(text=str(v))

    def _apply_effect(self, *, mode: int | None = None, name: str | None = None) -> None:
        mode_name = name or self._effect_var.get()
        self._effect_var.set(mode_name)
        mode_val = int(mode if mode is not None else self._effect_map.get(mode_name, 0))
        speed = int(self._speed_var.get())
        if not self._connected:
            self._toast("Not connected")
            return
        self._service.set_effect(mode_val, speed)

    def _save_scene(self) -> None:
        name = self._scene_name_var.get().strip()
        if not name:
            self._toast("Scene name required")
            return
        scene = {
            "name": name,
            "color": [self._r_var.get(), self._g_var.get(), self._b_var.get()],
            "brightness": int(self._brightness_var.get()),
            "effect": {"name": self._effect_var.get(), "speed": int(self._speed_var.get())},
            "power": bool(self._power_on),
        }
        scenes: list[dict[str, Any]] = list(self.cfg.data.get("scenes", []) or [])
        scenes = [s for s in scenes if s.get("name") != name]
        scenes.insert(0, scene)
        self.cfg.data["scenes"] = scenes
        self.cfg.save()
        self._scene_name_var.set("")
        self._render_scenes()
        self._toast("Scene saved")

    def _render_scenes(self) -> None:
        for child in self._scene_list.winfo_children():
            child.destroy()
        scenes: list[dict[str, Any]] = list(self.cfg.data.get("scenes", []) or [])
        if not scenes:
            ctk.CTkLabel(self._scene_list, text="No scenes saved yet.", text_color=("gray70", "gray70")).pack(
                padx=8, pady=8, anchor="w"
            )
            return
        for scene in scenes:
            row = ctk.CTkFrame(self._scene_list, corner_radius=8)
            row.pack(fill="x", padx=6, pady=4)
            row.grid_columnconfigure(0, weight=1)
            name = str(scene.get("name") or "Unnamed")
            ctk.CTkLabel(row, text=name).grid(row=0, column=0, padx=10, pady=8, sticky="w")
            ctk.CTkButton(row, text="Apply", width=70, command=lambda s=scene: self._apply_scene(s)).grid(
                row=0, column=1, padx=6, pady=8
            )
            ctk.CTkButton(row, text="Delete", width=70, fg_color="#7a2f2f", command=lambda n=name: self._del_scene(n)).grid(
                row=0, column=2, padx=(0, 8), pady=8
            )

    def _apply_scene(self, scene: dict[str, Any]) -> None:
        color = scene.get("color") or [255, 255, 255]
        brightness = int(scene.get("brightness") or 80)
        effect = scene.get("effect") or {}
        power = bool(scene.get("power", True))

        self._power_on = power
        self._power_btn.configure(text="POWER ON" if self._power_on else "POWER OFF")
        self._brightness_slider.set(brightness)
        self._on_brightness_slider(float(brightness))

        if isinstance(color, list) and len(color) == 3:
            self._set_color(int(color[0]), int(color[1]), int(color[2]), remember=True, send=False)

        eff_name = str(effect.get("name") or self._effect_var.get())
        if eff_name in self._effect_map:
            self._effect_var.set(eff_name)
        spd = int(effect.get("speed") or self._speed_var.get())
        self._speed_slider.set(spd)
        self._on_speed_slider(float(spd))

        if not self._connected:
            self._toast("Scene loaded (not connected)")
            return

        self._service.set_power(self._power_on)
        self._service.set_color(self._r_var.get(), self._g_var.get(), self._b_var.get())
        self._service.set_brightness_pct(int(self._brightness_var.get()))
        self._service.set_effect(int(self._effect_map.get(self._effect_var.get(), 0)), spd)

    def _del_scene(self, name: str) -> None:
        scenes: list[dict[str, Any]] = list(self.cfg.data.get("scenes", []) or [])
        scenes = [s for s in scenes if s.get("name") != name]
        self.cfg.data["scenes"] = scenes
        self.cfg.save()
        self._render_scenes()
        self._toast("Scene deleted")

    def _push_recent_color(self, rgb: list[int]) -> None:
        recent: list[list[int]] = list(self.cfg.data.get("recent_colors", []) or [])
        recent = [c for c in recent if c != rgb]
        recent.insert(0, rgb)
        recent = recent[:8]
        self.cfg.data["recent_colors"] = recent
        self.cfg.save()
        self._render_recent_colors()

    def _render_recent_colors(self) -> None:
        recent: list[list[int]] = list(self.cfg.data.get("recent_colors", []) or [])
        for i, btn in enumerate(self._recent_buttons):
            if i >= len(recent):
                btn.configure(text="—", command=lambda: None)
                continue
            r, g, b = recent[i]
            hex_color = self._rgb_to_hex(r, g, b)
            btn.configure(text=hex_color, command=lambda c=recent[i]: self._set_color(c[0], c[1], c[2]))

    def _bump_brightness(self, delta: int) -> None:
        v = int(self._brightness_var.get()) + int(delta)
        v = max(0, min(100, v))
        self._brightness_slider.set(v)
        self._on_brightness_slider(float(v))

    def _bump_speed(self, delta: int) -> None:
        v = int(self._speed_var.get()) + int(delta)
        v = max(0, min(255, v))
        self._speed_slider.set(v)
        self._on_speed_slider(float(v))

    def _on_ble_state_from_thread(self, state: ConnectionState) -> None:
        self.after(0, lambda: self._on_ble_state(state))

    def _on_last_command_from_thread(self, label: str) -> None:
        self.after(0, lambda: self._set_last_command(label))

    def _on_log_from_thread(self, msg: str) -> None:
        self.after(0, lambda: self._append_log(msg))

    def _on_ble_state(self, state: ConnectionState) -> None:
        self._connected = bool(state.connected)
        if state.device:
            self._device_label = f"{state.device.name} ({state.device.address})"
        else:
            self._device_label = ""
        if state.last_error and not self._connected:
            self._toast(state.last_error)
        self._connect_btn.configure(text="Disconnect" if self._connected else "Connect")
        self._refresh_status_bar()

    def _set_last_command(self, label: str) -> None:
        self._last_command = label
        self._refresh_status_bar()
        self._append_log(f"CMD: {label}")

    def _refresh_status_bar(self) -> None:
        self._dot.configure(text_color="green" if self._connected else "red")
        self._status_label.configure(text="Connected" if self._connected else "Disconnected")
        self._device_status.configure(text=self._device_label)
        self._cmd_status.configure(text=self._last_command)

    def _sync_preview(self) -> None:
        self._preview.itemconfig(self._preview_rect, fill=self._hex_var.get())

    def _toast(self, message: str) -> None:
        t = ctk.CTkToplevel(self)
        t.overrideredirect(True)
        t.attributes("-topmost", True)
        x = self.winfo_rootx() + 40
        y = self.winfo_rooty() + self.winfo_height() - 80
        t.geometry(f"+{x}+{y}")
        frame = ctk.CTkFrame(t, corner_radius=10)
        frame.pack(fill="both", expand=True)
        ctk.CTkLabel(frame, text=message, padx=12, pady=10).pack()
        t.after(2200, t.destroy)

    def _append_log(self, msg: str) -> None:
        self._logs.append(msg)
        self._logs = self._logs[-200:]
        self._debug_text.configure(state="normal")
        self._debug_text.delete("1.0", "end")
        self._debug_text.insert("end", "\n".join(self._logs) + "\n")
        self._debug_text.configure(state="disabled")

    def _poll_future(self, fut: "asyncio.Future", on_done: callable) -> None:
        if fut.done():
            on_done()
            return
        self.after(50, lambda: self._poll_future(fut, on_done))

    def _friendly_ble_error(self, e: Exception) -> str:
        msg = str(e).strip() or e.__class__.__name__
        if "Denied" in msg or "access" in msg.lower():
            return "Bluetooth access denied (check Windows Bluetooth permissions)."
        return msg

    def _rgb_to_hex(self, r: int, g: int, b: int) -> str:
        return f"#{r:02x}{g:02x}{b:02x}"

    def _on_close(self) -> None:
        try:
            self._ble.stop()
        except Exception:
            pass
        self.destroy()
