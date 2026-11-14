"""Binary packet format used by the experimental ARQ protocols."""

import struct

from config import MAX_PAYLOAD, MAX_SEQUENCE
from protocol.crc import calculate_crc, verify_crc

DATA = 0
ACK = 1
END = 2
VALID_TYPES = {DATA, ACK, END}


class Packet:
    HEADER_FORMAT = "!IBHI"
    HEADER_WITHOUT_CRC_FORMAT = "!IBH"
    HEADER_SIZE = struct.calcsize(HEADER_FORMAT)

    def __init__(self, sequence, packet_type, payload, crc=0):
        self.sequence = sequence
        self.packet_type = packet_type
        self.payload = payload
        self.crc = crc

    def _validate(self):
        if (not isinstance(self.sequence, int) or isinstance(self.sequence, bool)
                or not 0 <= self.sequence <= MAX_SEQUENCE):
            raise ValueError("Sequence number must be an unsigned 32-bit integer")
        if (not isinstance(self.packet_type, int) or isinstance(self.packet_type, bool)
                or self.packet_type not in VALID_TYPES):
            raise ValueError("Invalid packet type")
        if not isinstance(self.payload, (bytes, bytearray, memoryview)):
            raise ValueError("Payload must be bytes-like")
        if len(self.payload) > MAX_PAYLOAD:
            raise ValueError(f"Payload exceeds MAX_PAYLOAD ({MAX_PAYLOAD})")
        if self.packet_type == DATA and not self.payload:
            raise ValueError("DATA payload cannot be empty")
        if self.packet_type in (ACK, END) and self.payload:
            raise ValueError("ACK and END packets must have empty payloads")

    def encode(self):
        self._validate()
        payload = bytes(self.payload)
        header_without_crc = struct.pack(
            self.HEADER_WITHOUT_CRC_FORMAT,
            self.sequence,
            self.packet_type,
            len(payload),
        )
        checksum = calculate_crc(header_without_crc + payload)
        header = struct.pack(
            self.HEADER_FORMAT,
            self.sequence,
            self.packet_type,
            len(payload),
            checksum,
        )
        return header + payload

    @staticmethod
    def decode(data):
        if not isinstance(data, (bytes, bytearray, memoryview)):
            raise ValueError("Packet data must be bytes-like")
        data = bytes(data)
        if len(data) < Packet.HEADER_SIZE:
            raise ValueError("Packet too small")

        try:
            sequence, packet_type, length, checksum = struct.unpack(
                Packet.HEADER_FORMAT,
                data[:Packet.HEADER_SIZE],
            )
        except struct.error as exc:
            raise ValueError("Invalid packet header") from exc

        if packet_type not in VALID_TYPES:
            raise ValueError("Invalid packet type")
        if length > MAX_PAYLOAD:
            raise ValueError(f"Payload exceeds MAX_PAYLOAD ({MAX_PAYLOAD})")

        expected_length = Packet.HEADER_SIZE + length
        if len(data) < expected_length:
            raise ValueError("Incomplete packet")
        if len(data) > expected_length:
            raise ValueError("Unexpected trailing bytes")

        payload = data[Packet.HEADER_SIZE:]
        packet = Packet(sequence, packet_type, payload, checksum)
        packet._validate()

        checksum_input = struct.pack(
            Packet.HEADER_WITHOUT_CRC_FORMAT,
            sequence,
            packet_type,
            length,
        ) + payload
        if not verify_crc(checksum_input, checksum):
            raise ValueError("CRC mismatch")
        return packet

    def __repr__(self):
        return (
            f"Packet(sequence={self.sequence}, type={self.packet_type}, "
            f"payload_length={len(self.payload)})"
        )
