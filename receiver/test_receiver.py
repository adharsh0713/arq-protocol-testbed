import hashlib
import json
import socket

from config import load_config
from protocol.packet import ACK, DATA, END, Packet
from receiver.receiver import Receiver


ADDRESS = ("127.0.0.1", 5001)
OTHER_ADDRESS = ("127.0.0.1", 5999)


class FakeSocket:
    def __init__(self, incoming=()):
        self.incoming = list(incoming)
        self.sent = []
        self.timeout = None
        self.closed = False

    def settimeout(self, value):
        self.timeout = value

    def recvfrom(self, _size):
        if self.incoming:
            return self.incoming.pop(0)
        raise socket.timeout

    def sendto(self, data, address):
        self.sent.append((data, address))
        return len(data)

    def close(self):
        self.closed = True


def datagram(sequence, kind, payload=b"", address=ADDRESS):
    return Packet(sequence, kind, payload).encode(), address


def settings(protocol="selective_repeat", window=4, chunk_size=4096):
    return load_config({
        "PROTOCOL": protocol,
        "WINDOW_SIZE": str(window),
        "CHUNK_SIZE": str(chunk_size),
        "TIMEOUT": "0.01",
        "MAX_RETRIES": "2",
        "OUTPUT_FILE": "unused.bin",
    })


def ack_sequences(fake_socket):
    return [Packet.decode(data).sequence for data, _ in fake_socket.sent]


def make_receiver(tmp_path, fake_socket, protocol="selective_repeat", window=4, chunk_size=4096, **kwargs):
    output = tmp_path / "received.bin"
    return Receiver(
        settings(protocol, window=window, chunk_size=chunk_size),
        sock=fake_socket,
        output_file=output,
        metrics_path=tmp_path / "receiver.json",
        quiet=True,
        **kwargs,
    ), output


def test_receiver_module_import_has_no_socket_side_effect():
    import receiver.receiver as receiver_module

    assert isinstance(receiver_module.Receiver, type)
    assert not hasattr(receiver_module, "sock")


def test_selective_repeat_buffers_out_of_order_then_writes_in_order(tmp_path):
    source = b"firstsecond"
    fake = FakeSocket([
        datagram(1, DATA, b"econd"),
        datagram(0, DATA, b"firsts"),
        datagram(2, END),
    ])
    receiver, output = make_receiver(
        tmp_path,
        fake,
        chunk_size=6,
        expected_size=len(source),
        expected_sha256=hashlib.sha256(source).hexdigest(),
    )

    result = receiver.run()

    assert result["status"] == "completed"
    assert result["integrity_verified"] is True
    assert output.read_bytes() == source
    assert not (tmp_path / "received.bin.part").exists()
    assert ack_sequences(fake) == [1, 0, 2]
    assert result["unique_data_received"] == 2
    assert result["unique_data_delivered"] == 2
    assert receiver.receive_buffer == {}
    assert result["receive_buffer_remaining"] == 0
    assert result["effective_configuration"]["protocol"] == "selective_repeat"


def test_go_back_n_discards_out_of_order_and_reacks_last_cumulative_ack(tmp_path):
    fake = FakeSocket([
        datagram(1, DATA, b"B"),
        datagram(0, DATA, b"A"),
        datagram(0, DATA, b"A"),
        datagram(1, DATA, b"B"),
        datagram(2, END),
    ])
    receiver, output = make_receiver(tmp_path, fake, protocol="go_back_n")

    result = receiver.run()

    assert result["status"] == "completed"
    assert output.read_bytes() == b"AB"
    assert ack_sequences(fake) == [0, 0, 1, 2]
    assert result["duplicate_arrivals"] == 1
    assert result["out_of_window_discarded"] == 1


def test_stop_and_wait_does_not_ack_future_sequence(tmp_path):
    fake = FakeSocket([
        datagram(1, DATA, b"future"),
        datagram(0, DATA, b"now"),
        datagram(1, END),
    ])
    receiver, output = make_receiver(tmp_path, fake, protocol="stop_wait")

    result = receiver.run()

    assert result["status"] == "completed"
    assert output.read_bytes() == b"now"
    assert ack_sequences(fake) == [0, 1]
    assert result["out_of_window_discarded"] == 1


def test_selective_repeat_never_acks_sequence_beyond_receive_window(tmp_path):
    fake = FakeSocket([
        datagram(4, DATA, b"outside"),
        datagram(0, DATA, b"inside"),
        datagram(1, END),
    ])
    receiver, output = make_receiver(tmp_path, fake, window=4)

    result = receiver.run()

    assert result["status"] == "completed"
    assert output.read_bytes() == b"inside"
    assert ack_sequences(fake) == [0, 1]
    assert result["out_of_window_discarded"] == 1


def test_duplicate_corrupt_and_foreign_datagrams_do_not_duplicate_output(tmp_path):
    original = Packet(0, DATA, b"payload").encode()
    corrupted = bytearray(original)
    corrupted[-1] ^= 0x80
    fake = FakeSocket([
        (bytes(corrupted), ADDRESS),
        (original, ADDRESS),
        (original, ADDRESS),
        datagram(1, END, address=OTHER_ADDRESS),
        datagram(1, END),
    ])
    receiver, output = make_receiver(tmp_path, fake)

    result = receiver.run()

    assert result["status"] == "completed"
    assert output.read_bytes() == b"payload"
    assert result["corrupt_discarded"] == 1
    assert result["duplicate_arrivals"] == 1
    assert result["out_of_window_discarded"] == 1


def test_premature_end_is_rejected_and_partial_file_removed_on_idle_timeout(tmp_path):
    fake = FakeSocket([datagram(2, END)])
    receiver, output = make_receiver(tmp_path, fake)

    result = receiver.run()

    assert result["status"] == "idle_timeout"
    assert not output.exists()
    assert not (tmp_path / "received.bin.part").exists()
    assert result["error"].startswith("No valid datagram")


def test_integrity_mismatch_does_not_publish_partial_output(tmp_path):
    fake = FakeSocket([
        datagram(0, DATA, b"wrong"),
        datagram(1, END),
    ])
    receiver, output = make_receiver(
        tmp_path,
        fake,
        expected_size=5,
        expected_sha256=hashlib.sha256(b"right").hexdigest(),
    )

    result = receiver.run()

    assert result["status"] == "integrity_failed"
    assert result["integrity_verified"] is False
    assert not output.exists()
    assert not (tmp_path / "received.bin.part").exists()
    saved = json.loads((tmp_path / "receiver.json").read_text())
    assert saved["received_size"] == 5
    assert saved["received_sha256"] == hashlib.sha256(b"wrong").hexdigest()


def test_end_ack_is_repeated_during_linger(tmp_path):
    fake = FakeSocket([
        datagram(0, DATA, b"x"),
        datagram(1, END),
        datagram(1, END),
    ])
    receiver, _ = make_receiver(tmp_path, fake, end_ack_wait=0.02)

    result = receiver.run()

    assert result["status"] == "completed"
    assert ack_sequences(fake) == [0, 1, 1]


def test_receiver_metrics_saved_on_idle_failure(tmp_path):
    fake = FakeSocket([])
    receiver, _ = make_receiver(tmp_path, fake)

    receiver.run()

    saved = json.loads((tmp_path / "receiver.json").read_text())
    assert saved["status"] == "idle_timeout"
    assert saved["receive_buffer_remaining"] == 0


def test_aborted_selective_repeat_transfer_releases_buffer_and_partial_file(tmp_path):
    fake = FakeSocket([datagram(1, DATA, b"buffered")])
    receiver, output = make_receiver(tmp_path, fake)

    result = receiver.run()

    assert result["status"] == "idle_timeout"
    assert result["aborted_buffer_packets"] == 1
    assert result["receive_buffer_remaining"] == 0
    assert receiver.receive_buffer == {}
    assert not output.exists()
    assert not (tmp_path / "received.bin.part").exists()


def test_empty_file_is_committed_after_zero_sequence_end(tmp_path):
    empty_hash = hashlib.sha256(b"").hexdigest()
    fake = FakeSocket([datagram(0, END)])
    receiver, output = make_receiver(
        tmp_path,
        fake,
        expected_size=0,
        expected_sha256=empty_hash,
    )

    result = receiver.run()

    assert result["status"] == "completed"
    assert result["integrity_verified"] is True
    assert output.read_bytes() == b""
    assert ack_sequences(fake) == [0]


def test_selective_repeat_window_lower_exact_and_upper_boundaries(tmp_path):
    fake = FakeSocket([
        datagram(0, DATA, b"0"),
        datagram(0, DATA, b"duplicate"),
        datagram(4, DATA, b"4"),
        datagram(5, DATA, b"outside"),
        datagram(1, DATA, b"1"),
        datagram(2, DATA, b"2"),
        datagram(3, DATA, b"3"),
        datagram(5, END),
    ])
    receiver, output = make_receiver(tmp_path, fake, window=4)

    result = receiver.run()

    assert result["status"] == "completed"
    assert output.read_bytes() == b"01234"
    assert ack_sequences(fake) == [0, 0, 4, 1, 2, 3, 5]
    assert result["duplicate_arrivals"] == 1
    assert result["out_of_window_discarded"] == 1


def test_receiver_rejects_data_lengths_that_do_not_match_expected_chunk_boundaries(tmp_path):
    fake = FakeSocket([
        datagram(0, DATA, b"abc"),  # First chunk must be four bytes.
        datagram(1, END),
    ])
    receiver, output = make_receiver(
        tmp_path, fake, chunk_size=4, expected_size=5,
        expected_sha256=hashlib.sha256(b"abcde").hexdigest(),
    )
    result = receiver.run()
    assert result["invalid_chunk_discarded"] == 1
    assert result["data_arrivals"] == 1
    assert result["status"] == "idle_timeout"
    assert not output.exists()


def test_receiver_accepts_exact_chunk_then_short_final_chunk(tmp_path):
    source = b"abcde"
    fake = FakeSocket([
        datagram(0, DATA, b"abcd"),
        datagram(1, DATA, b"e"),
        datagram(2, END),
    ])
    receiver, output = make_receiver(
        tmp_path, fake, chunk_size=4, expected_size=len(source),
        expected_sha256=hashlib.sha256(source).hexdigest(),
    )
    result = receiver.run()
    assert result["status"] == "completed"
    assert output.read_bytes() == source
    assert result["invalid_chunk_discarded"] == 0
