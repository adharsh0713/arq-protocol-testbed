import os
import socket
import sys

import config
from algorithms.selector import get_protocol
from experiments.metrics import Metrics
from protocol.control import send_control_packet
from protocol.packet import DATA, END, Packet
from config import max_transfer_size


def send_file(filename):
    file_size = os.path.getsize(filename)
    max_file_size = max_transfer_size(config.CHUNK_SIZE)
    if file_size > max_file_size:
        raise ValueError(
            f"File exceeds the 32-bit sequence-space limit ({max_file_size} bytes)"
        )

    packets = []
    with open(filename, "rb") as source:
        sequence = 0
        while True:
            chunk = source.read(config.CHUNK_SIZE)
            if not chunk:
                break
            packets.append(Packet(sequence, DATA, chunk))
            sequence += 1

    metrics = Metrics(config.PROTOCOL, config.SETTINGS.to_dict())
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    destination = (config.SERVER_IP, config.SERVER_PORT)
    send_protocol = get_protocol(config.PROTOCOL)

    try:
        common = {
            "timeout": config.TIMEOUT,
            "max_retries": config.MAX_RETRIES,
        }
        if config.PROTOCOL == "stop_wait":
            send_protocol(sock, destination, packets, metrics, **common)
        else:
            send_protocol(
                sock,
                destination,
                packets,
                metrics,
                window_size=config.WINDOW_SIZE,
                **common,
            )

        end_packet = Packet(sequence, END, b"")
        send_control_packet(
            sock,
            destination,
            end_packet,
            metrics,
            timeout=config.TIMEOUT,
            max_retries=config.MAX_RETRIES,
        )
        metrics.stop_timer()
        metrics.save_json(
            os.environ.get("SENDER_METRICS_PATH", "data/results/sender_metrics.json"),
            file_size,
        )
        return metrics.report(file_size)
    finally:
        sock.close()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python -m sender.sender <file>")
    print(send_file(sys.argv[1]))
    print("File sent")
