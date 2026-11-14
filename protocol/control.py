import math
import socket
import time

from config import MAX_RETRIES, TIMEOUT
from protocol.packet import ACK, Packet


def send_control_packet(sock, address, packet, metrics, *, timeout=TIMEOUT,
                        max_retries=MAX_RETRIES):
    if (not isinstance(timeout, (int, float)) or isinstance(timeout, bool)
            or not math.isfinite(timeout) or timeout <= 0
            or not isinstance(max_retries, int) or isinstance(max_retries, bool)
            or max_retries < 0):
        raise ValueError("Invalid control retry parameters")
    encoded = packet.encode()
    try:
        retries = 0
        while True:
            sock.sendto(encoded, address)
            metrics.control_packet_sent(len(encoded), retransmission=retries > 0)
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
                    time.sleep(max(0.0, deadline - time.monotonic()))
                    break

                if source != address:
                    continue
                try:
                    ack = Packet.decode(data)
                except ValueError:
                    continue
                if ack.packet_type != ACK or ack.sequence != packet.sequence:
                    continue
                metrics.ack_received()
                return

            if retries >= max_retries:
                raise TimeoutError(
                    f"Control packet {packet.sequence} failed after "
                    f"{max_retries} retransmissions"
                )
            retries += 1
    finally:
        sock.settimeout(None)
