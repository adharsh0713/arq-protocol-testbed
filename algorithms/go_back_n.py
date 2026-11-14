import math
import socket
import time

from config import MAX_RETRIES, TIMEOUT, WINDOW_SIZE
from protocol.packet import ACK, Packet


class GoBackN:
    """Go-Back-N sender with a sliding cumulative-ACK window."""

    def __init__(self, sock, receiver_addr, metrics, *, timeout=TIMEOUT,
                 window_size=WINDOW_SIZE, max_retries=MAX_RETRIES):
        if (not isinstance(timeout, (int, float)) or isinstance(timeout, bool)
                or not math.isfinite(timeout) or timeout <= 0
                or not isinstance(window_size, int) or isinstance(window_size, bool)
                or window_size < 1
                or not isinstance(max_retries, int) or isinstance(max_retries, bool)
                or max_retries < 0):
            raise ValueError("Invalid Go-Back-N parameters")
        self.sock = sock
        self.receiver_addr = receiver_addr
        self.metrics = metrics
        self.timeout = timeout
        self.window_size = window_size
        self.max_retries = max_retries
        self.base = 0
        self.next_seq = 0
        self.sent_sequences = set()
        self.timeout_retries = 0
        self.deadline = None

    def send_file(self, packets):
        try:
            while self.base < len(packets):
                self.send_window(packets)
                self.wait_for_ack(packets)
        finally:
            self.sock.settimeout(None)

    def send_window(self, packets):
        while self.next_seq < len(packets) and self.next_seq < self.base + self.window_size:
            packet = packets[self.next_seq]
            sequence = packet.sequence
            encoded = packet.encode()
            self.sock.sendto(encoded, self.receiver_addr)
            self.metrics.data_packet_sent(sequence, len(encoded))
            if sequence in self.sent_sequences:
                self.metrics.retransmission(sequence)
            else:
                self.sent_sequences.add(sequence)
            if sequence == self.base:
                self.deadline = time.monotonic() + self.timeout
            self.next_seq += 1

    def _resend_outstanding(self, packets):
        for index in range(self.base, self.next_seq):
            packet = packets[index]
            encoded = packet.encode()
            self.sock.sendto(encoded, self.receiver_addr)
            self.metrics.data_packet_sent(packet.sequence, len(encoded))
            self.metrics.retransmission(packet.sequence)
        self.deadline = time.monotonic() + self.timeout

    def wait_for_ack(self, packets):
        while self.base < self.next_seq:
            remaining = self.deadline - time.monotonic()
            if remaining <= 0:
                self._handle_timeout(packets)
                return
            self.sock.settimeout(remaining)
            try:
                data, address = self.sock.recvfrom(65535)
            except socket.timeout:
                self._handle_timeout(packets)
                return
            except ConnectionResetError:
                time.sleep(max(0.0, self.deadline - time.monotonic()))
                self._handle_timeout(packets)
                return

            if address != self.receiver_addr:
                continue
            try:
                ack_packet = Packet.decode(data)
            except ValueError:
                continue
            if ack_packet.packet_type != ACK:
                continue

            ack_num = ack_packet.sequence
            if ack_num < self.base:
                self.metrics.duplicate_ack_received(ack_num)
                continue
            if ack_num >= self.next_seq:
                continue

            old_base = self.base
            self.metrics.cumulative_ack_received(old_base, ack_num)
            self.base = ack_num + 1
            self.timeout_retries = 0
            self.deadline = (
                time.monotonic() + self.timeout if self.base < self.next_seq else None
            )
            return

    def _handle_timeout(self, packets):
        if self.timeout_retries >= self.max_retries:
            raise TimeoutError(
                f"Go-Back-N failed: no cumulative ACK progress after "
                f"{self.max_retries} retransmissions at base sequence {self.base}"
            )
        self.timeout_retries += 1
        self._resend_outstanding(packets)


def send_file(sock, address, packets, metrics, *, timeout=TIMEOUT,
              window_size=WINDOW_SIZE, max_retries=MAX_RETRIES):
    GoBackN(
        sock,
        address,
        metrics,
        timeout=timeout,
        window_size=window_size,
        max_retries=max_retries,
    ).send_file(packets)
