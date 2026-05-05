from elk_led_controller.main import main as elk_main
from smart_light_hub.main import main as hub_main


if __name__ == "__main__":
    # Default to the original single-device controller for now.
    # Run Smart Hub MVP with: python -m smart_light_hub.main
    elk_main()
