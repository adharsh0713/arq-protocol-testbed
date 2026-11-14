# Fault Model

## Purpose and scope

The proxy is a controlled localhost fault injector for the project's three ARQ protocols. It injects independent packet-level faults in two directions:

- **DATA direction:** sender to receiver. DATA and END packets use this injector.
- **ACK direction:** receiver to sender. ACK packets use this injector.

The model is intended for repeatable comparisons of ARQ recovery behavior. It is not a general-purpose network emulator and does not reproduce the full behavior of an Internet path.

## Configuration

All values are loaded by `config.load_config()` and are included in the proxy's effective configuration report.

| Environment variable | Direction | Meaning | Default |
|---|---|---|---:|
| `DATA_LOSS_RATE` | DATA | Probability that an observed DATA/END datagram is dropped | `0.0` |
| `DATA_CORRUPTION_RATE` | DATA | Probability that one bit in the datagram is flipped | `0.0` |
| `DATA_DELAY` | DATA | Fixed base delay in seconds for each scheduled copy | `0.0` |
| `DATA_DUPLICATE_RATE` | DATA | Probability of scheduling one additional identical copy | `0.0` |
| `DATA_REORDER_RATE` | DATA | Probability of adding a reorder hold to an observed packet | `0.0` |
| `DATA_REORDER_DELAY` | DATA | Additional hold in seconds for packets selected for reordering | `0.05` |
| `ACK_LOSS_RATE` | ACK | Probability that an observed ACK datagram is dropped | `0.0` |
| `ACK_CORRUPTION_RATE` | ACK | Probability that one bit in the ACK datagram is flipped | `0.0` |
| `ACK_DELAY` | ACK | Fixed base delay in seconds for each scheduled copy | `0.0` |
| `ACK_DUPLICATE_RATE` | ACK | Probability of scheduling one additional identical copy | `0.0` |
| `ACK_REORDER_RATE` | ACK | Probability of adding a reorder hold to an observed ACK | `0.0` |
| `ACK_REORDER_DELAY` | ACK | Additional hold in seconds for ACKs selected for reordering | `0.05` |
| `SEED` | Both | Base seed for the directional random streams | `0` |
| `PROXY_STATS_PATH` | Proxy | Atomic JSON statistics output path | `data/results/proxy_metrics.json` |
| `PROXY_STATS_FLUSH_INTERVAL` | Proxy | Number of observed datagrams between periodic writes | `100` |

Rates must be in `[0, 1]`; delays must be finite and non-negative. A nonzero reorder rate requires a strictly positive corresponding reorder delay.

## Fault decision semantics

For each valid datagram observed by the proxy, its directional injector applies decisions in this order:

1. **Loss:** if selected, drop the datagram. No later fault decision is applied to a dropped datagram.
2. **Corruption:** if selected, flip exactly one randomly selected bit in the raw UDP datagram. This can corrupt header or payload bytes; the receiver/sender CRC check is responsible for discarding it.
3. **Base delay:** add the configured direction-specific delay to the scheduled release time.
4. **Reordering:** if selected, add the direction-specific reorder hold to the release time. A later-arriving packet without that extra hold can be delivered first.
5. **Duplication:** if selected, schedule one additional copy of the resulting datagram. Both copies pass through the same delivery queue.

END is part of the DATA direction and can therefore be lost, corrupted, delayed, duplicated, or reordered. ACK has its own independent settings.

The proxy does not call `sleep()` to implement packet delay. It stores scheduled copies in a min-heap keyed by release time and wakes the UDP socket receive loop at the next release deadline. A delayed DATA packet therefore does not block ACK forwarding, and a delayed ACK does not block DATA forwarding.

## Randomness and reproducibility

Each direction owns a separate `random.Random` instance. The DATA injector uses `SEED`; the ACK injector uses `SEED XOR 0xA5A5A5A5`. The process-global `random` state is not modified.

Given the same code version, effective configuration, seed, and sequence of observed datagrams, each direction reproduces the same fault decisions. Reproducibility is not guaranteed across code changes that alter the number or order of random draws; record the source revision as well as the seed in experiment results.

The experiment task list is generated in a stable order. Each task receives `base_seed + zero_based_task_ordinal`; filtering happens after this assignment so the same task retains its seed when a user narrows a matrix. The proxy uses that run seed for DATA and `SEED XOR 0xA5A5A5A5` for ACK. The seed and effective configuration are written to process reports and the CSV.

## Counters and realized rates

Each direction reports the following counts:

| Counter | Definition |
|---|---|
| `packets_seen` | Valid protocol datagrams entering that directional injector |
| `packets_dropped` | Observed datagrams dropped by the loss decision |
| `packets_corrupted` | Observed datagrams whose bytes were modified |
| `packets_duplicated` | Additional copies scheduled beyond the original |
| `packets_delayed` | Observed datagrams receiving base delay or a nonzero reorder hold |
| `reorder_scheduled` | Observed datagrams selected for an extra reorder hold |
| `packets_forwarded` | Scheduled datagram copies actually sent to the destination |
| `packets_reordered` | Delivered copies whose input arrival order is earlier than a copy already delivered in that direction |

Loss, corruption, duplication, base/reorder-delay event and scheduled-reordering rates are calculated against `packets_seen`, not against the number of copies forwarded. The `reorder_delivery_rate` is different: it is the count of copies observed arriving out of order divided by `packets_forwarded`. A configured probability is not a promise that one finite run will realize that exact fraction. Small packet counts can deviate substantially from the configured values. Interpret each rate alongside its denominator and raw counts. The analysis output also labels configured delay in seconds separately from the realized fraction of incoming packets assigned non-zero delay; these values have different units and are not subtracted or treated as directly equal.

Malformed datagrams rejected by the proxy's packet decoder are counted in the top-level `invalid_datagrams` total and are not assigned to a direction. A datagram forwarded by the proxy is not counted as a new proxy input packet.

## Routing and lifecycle constraints

- One proxy instance handles one sender and one active transfer at a time.
- The first valid DATA/END source address becomes the sender address. Datagrams from a second sender are rejected and counted in `unexpected_senders`.
- ACK datagrams are accepted only from the configured receiver address and are forwarded to the pinned sender.
- The proxy socket does not enable `SO_REUSEADDR`; where available, it uses `SO_EXCLUSIVEADDRUSE`.
- Statistics are written atomically to the configured path periodically and again on graceful shutdown.
- A local process can request shutdown by sending the documented `SHUTDOWN_DATAGRAM`; the proxy drains already scheduled deliveries before exiting and writes a final report. The Python helper is `network.proxy.request_shutdown()`.

## Model exclusions and interpretation

This model does not implement bandwidth caps, queue capacity/drop-tail behavior, correlated or burst loss, packet scheduling across multiple network hops, real WAN jitter, congestion control, path MTU discovery, NAT behavior, or multiple simultaneous senders/receivers. Corruption flips one bit and does not model malicious or adversarial traffic. The delay is a configured constant plus an optional reorder hold, not a sampled latency distribution.

Results must therefore be described as localhost fault-injection experiments. They are useful for comparing ARQ state machines under controlled conditions; they are not predictions of application performance on a real network.
