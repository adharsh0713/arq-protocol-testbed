import math
import socket
import time

from config import MAX_RETRIES, TIMEOUT, WINDOW_SIZE
from protocol.packet import ACK, Packet


def send_file(sock, address, packets, metrics, *, timeout=TIMEOUT,
              window_size=WINDOW_SIZE, max_retries=MAX_RETRIES):
    if (not isinstance(timeout, (int, float)) or isinstance(timeout, bool)
            or not math.isfinite(timeout) or timeout <= 0
            or not isinstance(window_size, int) or isinstance(window_size, bool)
            or window_size < 1
            or not isinstance(max_retries, int) or isinstance(max_retries, bool)
            or max_retries < 0):
        raise ValueError("Invalid Selective Repeat parameters")

    base = 0
    next_seq = 0
    total = len(packets)
    outstanding = {}  # sequence -> {retries, sent_at}
    acknowledged = set()

    def transmit(sequence, retransmission=False):
        encoded = packets[sequence].encode()
        sock.sendto(encoded, address)
        metrics.data_packet_sent(sequence, len(encoded))
        if retransmission:
            metrics.retransmission(sequence)
        state = outstanding.setdefault(sequence, {"retries": 0, "sent_at": 0.0})
        state["sent_at"] = time.monotonic()

    try:
        while base < total:
            while next_seq < total and next_seq < base + window_size:
                transmit(next_seq)
                next_seq += 1

            # Wait only until the nearest outstanding packet deadline.
            deadlines = [state["sent_at"] + timeout for state in outstanding.values()]
            if not deadlines:
                raise RuntimeError("Selective Repeat has no outstanding packet to recover")
            remaining = max(0.0, min(deadlines) - time.monotonic())
            sock.settimeout(remaining)

            try:
                data, source = sock.recvfrom(65535)
            except socket.timeout:
                pass
            except ConnectionResetError:
                time.sleep(remaining)
            else:
                if source == address:
                    try:
                        ack = Packet.decode(data)
                    except ValueError:
                        ack = None
                    if ack is not None and ack.packet_type == ACK:
                        sequence = ack.sequence
                        if sequence in outstanding:
                            metrics.ack_received(sequence)
                            del outstanding[sequence]
                            acknowledged.add(sequence)
                            while base in acknowledged:
                                acknowledged.remove(base)
                                base += 1
                        elif sequence < base or sequence in acknowledged:
                            metrics.duplicate_ack_received(sequence)

            # Timer checks run even when the received datagram was invalid,
            # foreign, duplicated or not an ACK.
            now = time.monotonic()
            for sequence, state in list(outstanding.items()):
                if now - state["sent_at"] < timeout:
                    continue
                if state["retries"] >= max_retries:
                    raise TimeoutError(
                        f"Selective Repeat failed for packet {sequence} "
                        f"after {max_retries} retransmissions"
                    )
                state["retries"] += 1
                transmit(sequence, retransmission=True)
    finally:
        sock.settimeout(None)
