import random
import struct

import pytest

from config import MAX_PAYLOAD
from protocol.packet import ACK, DATA, END, Packet


@pytest.mark.parametrize(
    "packet_type,payload",
    [
        (DATA, b"Hello, world!"),
        (ACK, b""),
        (END, b""),
        (DATA, bytes(range(256))),
        (DATA, b"x" * MAX_PAYLOAD),
    ],
)
def test_packet_encode_decode_round_trip(packet_type, payload):
    original = Packet(7, packet_type, payload)
    decoded = Packet.decode(original.encode())
    assert decoded.sequence == original.sequence
    assert decoded.packet_type == original.packet_type
    assert decoded.payload == original.payload


def test_packet_format_is_11_byte_big_endian_header():
    packet = Packet(0x01020304, DATA, b"abc")
    encoded = packet.encode()
    sequence, packet_type, length, _crc = struct.unpack("!IBHI", encoded[:11])
    assert (sequence, packet_type, length) == (0x01020304, DATA, 3)
    assert encoded[:4] == b"\x01\x02\x03\x04"
    assert len(encoded) == 11 + 3


@pytest.mark.parametrize("length", range(11))
def test_decode_rejects_every_truncated_header_length(length):
    with pytest.raises(ValueError):
        Packet.decode(b"\x00" * length)


def test_decode_rejects_corruption_in_every_header_byte():
    encoded = bytearray(Packet(7, DATA, b"payload").encode())
    for index in range(Packet.HEADER_SIZE):
        corrupted = bytearray(encoded)
        corrupted[index] ^= 0x01
        with pytest.raises(ValueError):
            Packet.decode(corrupted)


def test_decode_rejects_corrupted_payload_and_trailing_bytes():
    encoded = bytearray(Packet(1, DATA, b"hello").encode())
    encoded[-1] ^= 0x01
    with pytest.raises(ValueError, match="CRC mismatch"):
        Packet.decode(encoded)
    with pytest.raises(ValueError, match="trailing"):
        Packet.decode(Packet(1, DATA, b"hello").encode() + b"\x00")


def test_encode_and_decode_reject_oversize_payloads():
    with pytest.raises(ValueError, match="MAX_PAYLOAD"):
        Packet(0, DATA, b"x" * (MAX_PAYLOAD + 1)).encode()

    header = struct.pack("!IBHI", 0, DATA, MAX_PAYLOAD + 1, 0)
    with pytest.raises(ValueError, match="MAX_PAYLOAD"):
        Packet.decode(header)


@pytest.mark.parametrize(
    "packet",
    [
        Packet(-1, DATA, b"x"),
        Packet(1 << 32, DATA, b"x"),
        Packet(0, 99, b"x"),
        Packet(0, ACK, b"unexpected"),
        Packet(0, END, b"unexpected"),
        Packet(0, DATA, b""),
        Packet(0, DATA, "not bytes"),
    ],
)
def test_encode_rejects_invalid_packet_fields(packet):
    with pytest.raises(ValueError):
        packet.encode()


def test_random_input_never_raises_non_value_error():
    rng = random.Random(20261113)
    for _ in range(10_000):
        data = rng.randbytes(rng.randrange(0, 96))
        try:
            Packet.decode(data)
        except ValueError:
            pass


def test_repr_reports_payload_length_not_payload_contents():
    packet = Packet(2, DATA, b"secret-payload")
    rendered = repr(packet)
    assert "payload_length=14" in rendered
    assert "secret-payload" not in rendered
