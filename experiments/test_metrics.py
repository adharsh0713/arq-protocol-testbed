import time

from experiments.metrics import Metrics


def test_metrics_counts_packets_and_retransmissions():
    metrics = Metrics("go_back_n")

    metrics.data_packet_sent()
    metrics.data_packet_sent()
    metrics.control_packet_sent()
    metrics.packet_received()
    metrics.ack_sent()
    metrics.ack_received()
    metrics.retransmission()

    report = metrics.report(file_size=1000)

    assert report["protocol"] == "go_back_n"
    assert report["file_size"] == 1000
    assert report["data_packets_sent"] == 2
    assert report["control_packets_sent"] == 1
    assert report["packets_received"] == 1
    assert report["acks_sent"] == 1
    assert report["acks_received"] == 1
    assert report["retransmissions"] == 1


def test_metrics_completion_time_and_throughput():
    metrics = Metrics("go_back_n")

    metrics.start_timer()
    time.sleep(0.05)
    metrics.stop_timer()

    duration = metrics.completion_time()
    throughput = metrics.throughput(1000)

    assert duration >= 0.05
    assert throughput > 0


def test_metrics_without_timer_returns_zero():
    metrics = Metrics("go_back_n")

    assert metrics.completion_time() == 0
    assert metrics.throughput(1000) == 0

def test_metrics_counts_encoded_bytes_and_end_retries_separately():
    metrics = Metrics("selective_repeat")

    metrics.data_packet_sent(sequence=0, encoded_bytes=75)
    metrics.data_packet_sent(sequence=1, encoded_bytes=31)
    metrics.control_packet_sent(encoded_bytes=11)
    metrics.control_packet_sent(encoded_bytes=11, retransmission=True)

    report = metrics.report(file_size=95)
    assert report["total_bytes_sent"] == 128
    assert report["data_packets_sent"] == 2
    assert report["control_packets_sent"] == 2
    assert report["end_retries"] == 1
    assert report["retransmissions"] == 0


def test_metrics_records_packet_recovery_and_duplicate_ack_for_retransmission():
    metrics = Metrics("go_back_n")

    metrics.data_packet_sent(sequence=4, encoded_bytes=100)
    metrics.retransmission(sequence=4)
    time.sleep(0.003)
    metrics.cumulative_ack_received(4, 4)
    metrics.duplicate_ack_received(sequence=4)

    report = metrics.report(file_size=89)
    assert report["retransmitted_packets"] == 1
    assert report["recovery_samples"] == 1
    assert report["recovery_time_mean"] >= 0.002
    assert report["recovery_time_max"] == report["recovery_time_mean"]
    assert report["duplicate_acks_received"] == 1
    assert report["duplicate_acks_for_retransmitted_packets"] == 1
