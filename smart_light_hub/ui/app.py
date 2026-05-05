from __future__ import annotations

import asyncio
import tkinter as tk
from typing import Any

import customtkinter as ctk

from ..core.engine import CoreEngine
from ..services.light import LightService


class HubApp(ctk.CTk):
    def __init__(self, engine: CoreEngine) -> None:
        super().__init__()
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.engine = engine
        self.light = LightService(engine)

        self.title("Smart Light Hub (MVP)")
        self.geometry("700x560")
        self.resizable(False, False)

        self._entity_var = tk.StringVar(value="")
        self._on_var = tk.BooleanVar(value=True)
        self._r = tk.IntVar(value=255)
        self._g = tk.IntVar(value=100)
        self._b = tk.IntVar(value=0)
        self._brightness = tk.IntVar(value=80)

        self._debounce: str | None = None

        self._build_ui()
        self.after(150, self._refresh_entities)

    def _build_ui(self) -> None:
        root = ctk.CTkFrame(self, corner_radius=12)
        root.pack(fill="both", expand=True, padx=16, pady=16)
        root.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(root, text="Entity").grid(row=0, column=0, padx=12, pady=(12, 6), sticky="w")
        self._entity_menu = ctk.CTkOptionMenu(root, variable=self._entity_var, values=["(no devices)"])
        self._entity_menu.grid(row=0, column=1, padx=12, pady=(12, 6), sticky="ew")

        self._toggle = ctk.CTkSwitch(root, text="Power", variable=self._on_var, command=self._apply_power)
        self._toggle.grid(row=1, column=0, padx=12, pady=10, sticky="w")

        preview = tk.Canvas(root, width=60, height=22, highlightthickness=0)
        preview.grid(row=1, column=1, padx=12, pady=10, sticky="w")
        self._preview = preview
        self._preview_rect = preview.create_rectangle(0, 0, 60, 22, outline="", fill="#ff6400")

        self._slider_row(root, "R", 2, self._r)
        self._slider_row(root, "G", 3, self._g)
        self._slider_row(root, "B", 4, self._b)

        ctk.CTkLabel(root, text="Brightness").grid(row=5, column=0, padx=12, pady=(12, 6), sticky="w")
        self._bri = ctk.CTkSlider(root, from_=0, to=100, number_of_steps=100, command=self._on_change)
        self._bri.set(self._brightness.get())
        self._bri.grid(row=5, column=1, padx=12, pady=(12, 6), sticky="ew")

        self._log = ctk.CTkTextbox(root, height=180)
        self._log.grid(row=6, column=0, columnspan=2, padx=12, pady=(12, 12), sticky="nsew")
        self._log.insert("end", "State-driven MVP UI.\n")
        self._log.configure(state="disabled")

        # Subscribe to engine events (runs in hub loop thread); marshal to UI thread.
        async def on_event(evt):
            self.after(0, lambda: self._append_log(f"{evt.name}: {evt.data}"))

        self.engine.events.subscribe("state_changed", on_event)
        self.engine.events.subscribe("device_missing", on_event)
        self.engine.events.subscribe("device_applied", on_event)

    def _slider_row(self, parent: ctk.CTkFrame, label: str, row: int, var: tk.IntVar) -> None:
        ctk.CTkLabel(parent, text=label).grid(row=row, column=0, padx=12, pady=6, sticky="w")
        slider = ctk.CTkSlider(parent, from_=0, to=255, number_of_steps=255, command=lambda _v: self._on_change())
        slider.set(var.get())
        slider.grid(row=row, column=1, padx=12, pady=6, sticky="ew")

        def sync(*_a: Any) -> None:
            slider.set(var.get())
            self._on_change()

        var.trace_add("write", sync)

    def _refresh_entities(self) -> None:
        devices = self.engine.registry.list()
        values = [d.entity_id for d in devices] or ["(no devices)"]
        self._entity_menu.configure(values=values)
        if not self._entity_var.get() or self._entity_var.get() not in values:
            self._entity_var.set(values[0])

    def _apply_power(self) -> None:
        entity_id = self._entity_var.get()
        if not entity_id or entity_id.startswith("("):
            return
        on = bool(self._on_var.get())
        fut = self.engine.submit(self.light.set_state(entity_id, {"on": on}))
        self._poll(fut)

    def _on_change(self) -> None:
        self._brightness.set(int(round(self._bri.get())))
        self._update_preview()
        if self._debounce:
            self.after_cancel(self._debounce)
        self._debounce = self.after(80, self._apply_color_and_brightness)

    def _apply_color_and_brightness(self) -> None:
        self._debounce = None
        entity_id = self._entity_var.get()
        if not entity_id or entity_id.startswith("("):
            return
        r, g, b = int(self._r.get()), int(self._g.get()), int(self._b.get())
        bri = int(self._brightness.get())

        async def apply() -> None:
            await self.light.set_state(entity_id, {"color": [r, g, b], "brightness": bri})

        fut = self.engine.submit(apply())
        self._poll(fut)

    def _update_preview(self) -> None:
        hex_color = f"#{int(self._r.get()):02x}{int(self._g.get()):02x}{int(self._b.get()):02x}"
        self._preview.itemconfig(self._preview_rect, fill=hex_color)

    def _append_log(self, msg: str) -> None:
        self._log.configure(state="normal")
        self._log.insert("end", msg + "\n")
        self._log.see("end")
        self._log.configure(state="disabled")

    def _poll(self, fut: "asyncio.Future") -> None:
        if fut.done():
            try:
                fut.result()
            except Exception as e:
                self._append_log(f"ERROR: {e}")
            return
        self.after(50, lambda: self._poll(fut))

