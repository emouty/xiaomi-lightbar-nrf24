import paho.mqtt.client as mqtt

from mqtt.subscriber import MqttController
from xiaomi_lightbar import Lightbar
import argparse

from xiaomi_lightbar.radio import RF24Wrapper

description = """
    MQTT subscriber for Xiaomi Lightbar Home Assistant MQTT Light integration.
    This script subscribes to the MQTT topic and controls the Xiaomi Lightbar based on the received messages by using the xiaomi_lightbar library.
"""

parser = argparse.ArgumentParser(description=description, formatter_class=argparse.RawDescriptionHelpFormatter)

parser.add_argument("--broker", type=str, default="homeassistant.local", help="MQTT Broker")
parser.add_argument("--port", type=int, default=1883, help="MQTT Port")
parser.add_argument("--username", type=str, default="", help="MQTT Username")
parser.add_argument("--password", type=str, default="", help="MQTT Password")
parser.add_argument("--topic", type=str, default="xiaomi/lightbar", help="MQTT Topic")
parser.add_argument("--ce_pin", type=int, default=25, help="CE Pin")
parser.add_argument("--csn_pin", type=int, default=0, help="CSN Pin")
parser.add_argument("--remote_id", type=lambda x: int(x, 16), default=0xABCDEF, help="Remote ID")

args = parser.parse_args()

CE_PIN = args.ce_pin
CSN_PIN = args.csn_pin
REMOTE_ID = args.remote_id
BROKER = args.broker
PORT = args.port
USERNAME = args.username
PASSWORD = args.password
TOPIC = args.topic


def main():
    try:
        radio_wrapper = RF24Wrapper(ce_pin=CE_PIN, csn_pin=CSN_PIN)
        # Create Lightbar and MqttController instances
        lightbar = Lightbar(radio_wrapper=radio_wrapper.radio, remote_id=REMOTE_ID)
        with MqttController(BROKER, PORT, USERNAME, PASSWORD, TOPIC, lightbar) as controller:
            controller.start()
            while True:  # Keep the program running
                pass
    except KeyboardInterrupt:
        print("\nInterrupted by user. Exiting...")


if __name__ == "__main__":
    main()
