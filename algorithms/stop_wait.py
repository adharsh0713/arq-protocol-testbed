import math
import socket
import time

from config import MAX_RETRIES, TIMEOUT
from protocol.packet import ACK, Packet


def send_file(sock, address, packets, metrics, *, timeout=TIMEOUT, max_retries=MAX_RETRIES):
    if (not isinstance(timeout, (int, float)) or isinstance(timeout, bool)
            or not math.isfinite(timeout) or timeout <= 0
            or not isinstance(max_retries, int) or isinstance(max_retries, bool)
            or max_retries < 0):
        raise ValueError("Invalid Stop-and-Wait parameters")
    for packet in packets:
        send_packet(
            sock,
            address,
            packet,
            metrics,
            timeout=timeout,
            max_retries=max_retries,
        )


def send_packet(sock, address, packet, metrics, *, timeout=TIMEOUT, max_retries=MAX_RETRIES):
    retries = 0
    encoded = packet.encode()

    while True:
        sock.sendto(encoded, address)
        metrics.data_packet_sent(packet.sequence, len(encoded))
        if retries:
            metrics.retransmission(packet.sequence)

        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            sock.settimeout(remaining)
            try:
                data, source = sock.recvfrom(65535)
            except socket.timeout:
                break
            except ConnectionResetError:
                # A reset must not create a tight retry loop on Windows UDP sockets.
                time.sleep(max(0.0, deadline - time.monotonic()))
                break

            if source != address:
                continue
            try:
                ack = Packet.decode(data)
            except ValueError:
                continue
            if ack.packet_type != ACK:
                continue
            if ack.sequence != packet.sequence:
                if ack.sequence < packet.sequence:
                    metrics.duplicate_ack_received(ack.sequence)
                continue

            metrics.ack_received(packet.sequence)
            sock.settimeout(None)
            return True

        if retries >= max_retries:
            sock.settimeout(None)
            raise TimeoutError(
                f"Packet {packet.sequence} failed after {max_retries} retransmissions"
            )
        retries += 1

