from __future__ import annotations

from .app import LedControllerApp


def main() -> None:
    app = LedControllerApp(config_path="config.json")
    app.mainloop()


if __name__ == "__main__":
    main()

