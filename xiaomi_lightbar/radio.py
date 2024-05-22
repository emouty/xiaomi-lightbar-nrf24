import time
from enum import Enum, auto
from struct import unpack

import crc
import pyrf24
from pyrf24 import RF24

from . import baseband


# https://nrf24.github.io/RF24/
# https://pyrf24.readthedocs.io/en/latest/rf24_api.html


def clamp(x: int):
    """Clamp value to [0, 15]"""
    return min(max(x, 0), 15)


PREAMBLE = 0x533914DD1C493412  # 8 bytes

def init_rf24(ce_pin, csn_pin):
    radio = pyrf24.RF24()
    if not radio.begin(ce_pin, csn_pin):
        raise OSError("nRF24L01 hardware is not responding")
    radio.channel = 6  # 6, 15, 43, 68 (or +1) -> 2406 MHz, 2015 MHz, 2043 MHz, 2068 MHz
    radio.pa_level = pyrf24.RF24_PA_LOW
    radio.data_rate = pyrf24.RF24_2MBPS
    radio.set_retries(0, 0)  # no repetitions, done manually in method send
    radio.listen = False
    radio.dynamic_payloads = False
    radio.payload_size = 17
    radio.open_tx_pipe(bytes(5 * [0x55]))  # Address, really sync sequence
    radio.listen = False
    return radio


class RF24Wrapper:
    class ReceiverOccupiedError(Exception):
        pass

    class MODE(Enum):
        READ = auto()
        WRITE = auto()

    def __init__(self, ce_pin: int, csn_pin: int, ):
        self.radio = pyrf24.RF24()
        if not self.radio.begin(ce_pin, csn_pin):
            raise OSError("nRF24L01 hardware is not responding")
        self.radio.channel = 6  # 6, 15, 43, 68 (or +1) -> 2406 MHz, 2015 MHz, 2043 MHz, 2068 MHz
        self.radio.pa_level = pyrf24.RF24_PA_LOW
        self.radio.data_rate = pyrf24.RF24_2MBPS
        self.radio.set_retries(0, 0)  # no repetitions, done manually in method send
        self.tx_occurring = False

    def switch_mode(self, mode: MODE):
        if not self.tx_occurring:
            if mode == RF24Wrapper.MODE.READ:
                self.radio.open_rx_pipe(1, PREAMBLE >> 24)  # 5 first bytes of preamble
                self.radio.listen = True
            elif mode == RF24Wrapper.MODE.WRITE:
                self.radio.open_tx_pipe(bytes(5 * [0x55]))  # Address, really sync sequence
                self.radio.listen = False
        else:
            raise RF24Wrapper.ReceiverOccupiedError("Reading is being done on rf24 can't switch to write mode")

    def try_switch_mode(self, mode: MODE, max_retries=3, delay_ms=100, fallback=None):
        for attempt in range(max_retries):
            try:
                self.switch_mode(mode)
                print("Switched to write mode")
                return  # Exit if successful
            except RF24Wrapper.ReceiverOccupiedError as e:
                print(f"Attempt {attempt + 1} failed: {e}")
                if attempt < max_retries - 1:
                    time.sleep(delay_ms / 1000)  # Wait before retrying
                else:
                    if fallback:
                        fallback()  # Execute fallback if provided
                    else:
                        print("Fallback: Could not switch to write mode after multiple attempts")


class Lightbar:
    """Implements a Xiaomi light bar controller with a nRF24L01 module"""

    def __init__(self, radio: RF24, remote_id: int):
        self.radio = radio
        self.repetitions = 20
        self.delay_s = 0.01
        self.counter = 0
        self.id = remote_id  # Xiaomi remote id, 3-byte int (0x112233)

    @classmethod
    def with_radio(cls, ce_pin: int, csn_pin: int, remote_id: int):
        instance = cls.__new__(cls)
        instance.radio = init_rf24(ce_pin, csn_pin)
        instance.repetitions = 20
        instance.delay_s = 0.01
        instance.counter = 0
        instance.id = remote_id
        return instance

    def send(self, code: int, counter: int = None):
        """Send a command to the Xiaomi light bar.

        Arguments:
        code: 2 byte int (e.g. 0x0100)
        counter: int in range(0, 256) to reject repeated packets.
                 If None, use an internal counter that increments one.
        """
        if counter is None:
            counter = self.counter
            self.counter += 1
            if self.counter > 255:
                self.counter = 0
        pkt = baseband.packet(self.id, code, counter)
        for _ in range(self.repetitions):
            self.radio.write(pkt)
            time.sleep(self.delay_s)

    @property
    def is_available(self):
        return self.radio.is_chip_connected

    def on_off(self, counter: int = None):
        self.send(0x0100, counter)

    def reset(self, counter: int = None):
        self.send(0x0600, counter)

    def cooler(self, step: int = 1, counter: int = None):
        self.send(0x0200 + clamp(step), counter)

    def warmer(self, step: int = 1, counter: int = None):
        self.send(0x0300 - clamp(step), counter)

    def higher(self, step: int = 1, counter: int = None):
        self.send(0x0400 + clamp(step), counter)

    def lower(self, step: int = 1, counter: int = None):
        self.send(0x0500 - clamp(step), counter)

    def brightness(self, value: int, counter: int = None):
        """Set the brightness (≤0 lowest, ≥15 highest 270 lm)"""

        # Beware, counter increases by two, two operations
        counter2 = None if counter is None else counter + 1

        # Saturate lowest sending an out-of-range step >15.
        # This delays the change until next update! Then adjust.
        self.send(0x0500 - 16, counter)
        self.higher(value, counter2)

    def color_temp(self, value: int, counter: int = None):
        """Set the color temperature (≤0 ~2700K, ≥15 ~6500K)"""

        # Beware, counter increases by two, two operations
        counter2 = None if counter is None else counter + 1

        # Saturate warmest sending an out-of-range step >15.
        # This delays the change until next update! Then adjust.
        self.send(0x0300 - 16, counter)
        self.cooler(value, counter2)


def strip_bits(num: int, msb: int, lsb: int):
    """Strip msb and lsb bits of an int"""

    mask = (1 << num.bit_length() - msb) - 1
    return (num & mask) >> lsb


def decode_packet(raw: bytes):
    """Decode a received packet

    I captured 12 bytes = 96 bits, but:
    - The first 15 bits (MSB) are the preamble trailing ones.
      Remember that the 24 LSB from the preamble were included in the captured packet.
      Where the other 9 bits are gone, I do not know. Maybe the ether monster ate them.
    - 9 bytes = 72 bits are the good ones, the payload.
    - The remaining 9 bits (LSB) are junk.
    """

    # Strip the preamble and junk bits
    raw_int = int.from_bytes(raw, "big")
    data = strip_bits(raw_int, 15, 9)

    # Now, the payload is clean and ready to be decoded
    keys = ["id", "separator", "counter", "command", "crc"]
    values = unpack('>3s s s 2s 2s', data.to_bytes(9, 'big'))
    values = (int.from_bytes(x, "big") for x in values)
    packet = dict(zip(keys, values))
    return packet


class Remote:

    def __init__(self, radio: RF24):
        self.radio = radio
        crc16_config = crc.Configuration(
            width=16,
            polynomial=0x1021,
            init_value=0xFFFE,
            final_xor_value=0x0000,
            reverse_input=False,
            reverse_output=False,
        )
        self.crc16 = crc.Calculator(crc16_config)

    def good_packet(self, packet: int):
        """Check the CRC of a packet"""

        x = Remote.PREAMBLE.to_bytes(8, 'big')
        x += packet["id"].to_bytes(3, 'big')
        x += packet["separator"].to_bytes(1, 'big')
        x += packet["counter"].to_bytes(1, 'big')
        x += packet["command"].to_bytes(2, 'big')
        return packet["crc"] == self.crc16.checksum(x)

    def print_packet(self, packet: int):
        if self.good_packet(packet):
            print("Decoded packet, CRC ok")
        else:
            print("Decoded packet, wrong CRC")
        for k, v in packet.items():
            print(f"• {k}: {hex(v)}")

    def read_and_print(self):
        has_payload, pipe_number = self.radio.available_pipe()
        if has_payload:
            received = self.radio.read(self.radio.payload_size)
            packet = decode_packet(received)
            print()
            self.print_packet(packet)
