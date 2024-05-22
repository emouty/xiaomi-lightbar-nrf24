#!/usr/bin/env python3

import argparse
import time

import pyrf24

from xiaomi_lightbar.radio import Remote

# https://pyrf24.readthedocs.io/en/latest/


description = """
    Script to capture and analyze a packet of the original remote for the Xiaomi Mi Computer Monitor Lightbar (non-BLE version), 
    using a nRF24L01 transceiver connected to a Raspberry Pi.

    - See https://github.com/lamperez/xiaomi-lightbar-nrf24/blob/main/readme.md for the dependencies and installation.
    - Modify CE_PIN and CS_PIN as needed.
    - Run the script.
    - Put the remote close to the nRF24L01 and operate it, turning the knob.

    The script will dump detected packets. Choose a packet with correct crc. Most of the packets are not detected, so you may need 
    to try long enough to capture at least one correct packet to obtain the device ID of the remote. You may also change CHANNEL to
    6, 15, 43 or 68 (or even 7, 16, 44 or 69) to try to increase the detection rate.
"""

parser = argparse.ArgumentParser(description=description, formatter_class=argparse.RawDescriptionHelpFormatter)

parser.add_argument("-c", "--channel", type=int,default=6, help="6 (default), 15, 43, 68 (or +1) -> 2406 MHz, 2043 MHz, 2068 MH")
parser.add_argument("-p", "--power", type=str, default="LOW", choices=["MIN", "LOW", "HIGH", "MAX"], help="Change the power level")

args = parser.parse_args()

# Set the power level
if args.power == "MIN":
    POW = pyrf24.RF24_PA_MIN
elif args.power == "LOW":
    POW = pyrf24.RF24_PA_LOW
elif args.power == "HIGH":
    POW = pyrf24.RF24_PA_HIGH
elif args.power == "MAX":
    POW = pyrf24.RF24_PA_MAX

CHANNEL = args.channel # 6 (default), 15, 43, 68 (or +1) -> 2406 MHz, 2043 MHz, 2068 MHz
CE_PIN = 25
CS_PIN = 0

PREAMBLE = 0x533914DD1C493412  # 8 bytes

radio = pyrf24.RF24()
if not radio.begin(CE_PIN, CS_PIN):
    raise OSError("nRF24L01 hardware is not responding")
radio.channel = CHANNEL
radio.pa_level = POW
radio.data_rate = pyrf24.RF24_2MBPS
radio.dynamic_payloads = False
radio.crc_length = pyrf24.RF24_CRC_DISABLED
radio.payload_size = 12  # More than necessary, I will strip some bits
radio.address_width = 5
radio.listen = True
radio.open_rx_pipe(1, PREAMBLE >> 24)  # 5 first bytes of preable
radio.print_details()
print(f"CHANNEL         = {CHANNEL}")

remote = Remote(radio)

while True:
    remote.read_and_print()
    time.sleep(0.1)
