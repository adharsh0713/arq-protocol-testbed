# Reliable UDP - Design Decisions and Justifications

This record explains the implementation choices and their trade-offs. It distinguishes deliberate scope decisions from defects that must be corrected. Measurements are not used as justification until they exist in the results CSV.

## D01 - Retain the 11-byte binary packet header

**Decision:** Keep `!IBHI`: unsigned 32-bit sequence number, unsigned 8-bit packet type, unsigned 16-bit payload length, and unsigned 32-bit CRC. All fields are big-endian.

**Reason:** The supplied checklist explicitly identifies the existing header as sound. Retaining it avoids changing the protocol surface while correcting the surrounding validation and ARQ behavior.

**Trade-off:** A custom header is intentionally small and easy to inspect, but it is not a standardized interoperable transport format.

## D02 - CRC covers all semantic packet fields

**Decision:** CRC32 covers sequence, type, length, and payload (the CRC field itself is excluded).

**Reason:** Corruption in sequence/type/length must be detected, not only corruption in the payload. A corrupted ACK must never be accepted as proof of delivery.

**Trade-off:** CRC detects accidental corruption; it is not authentication and does not prevent deliberate packet forgery.

## D03 - Enforce one maximum payload and the UDP datagram limit

**Decision:** Set `MAX_PAYLOAD` to 60,000 bytes and keep the configured chunk size at or below that value. The default chunk remains 4,096 bytes.

**Reason:** A declared 16-bit length alone would allow packets larger than the application's chosen safe datagram size. Explicit encode/decode checks make oversized input fail before it enters the ARQ logic. A 60,000-byte payload plus the 11-byte header remains below the 65,507-byte IPv4 UDP payload ceiling.

**Trade-off:** The maximum is a protocol implementation constraint, not a recommendation to use 60 KB packets on every network. The default chunk is smaller and can be varied consistently in experiments.

## D04 - Do not wrap 32-bit sequence numbers in v1.0

**Decision:** Sequence values are unsigned 32-bit integers and never wrap. The sender refuses files whose DATA packet count would make the following END sequence unrepresentable. END carries the next expected sequence, so the DATA packet count itself must be at most `2^32 - 1`.

**Reason:** Correct modular sequence arithmetic requires additional rules for window ambiguity and wraparound. It is unnecessary for the intended experimental files. With 4,096-byte chunks, the practical file-size ceiling is `4,096 × (2^32 - 1)` bytes (approximately 16 TiB).

**Trade-off:** Very large files beyond the sequence-space capacity are unsupported. This limit is documented rather than hidden.

## D05 - Use a configurable 50 ms localhost timeout by default

**Decision:** Use `TIMEOUT=0.05` seconds as the default for the localhost testbed, with an environment override. Keep the value constant within each matched experiment.

**Reason:** The supplied checklist measured roughly millisecond localhost behavior and identified a 1-second timeout as the dominant source of avoidable loss stalls. A 50 ms default reduces waiting while leaving margin over nominal loopback latency.

**Trade-off:** Too-short timeouts can cause spurious retransmissions, particularly under injected delay. RQ5 measures timeout sensitivity; the default is not advertised as a WAN setting.

## D06 - Make sender parameters explicit

**Decision:** Sender functions accept timeout, retry limit, and (for windowed protocols) window size as arguments with defaults.

**Reason:** Explicit parameters are easier to test, avoid monkeypatching imported module constants, and let the experiment runner keep a matched parameter set across runs.

**Trade-off:** Call sites must pass the effective settings; the process configuration must therefore be validated and recorded.

## D07 - Go-Back-N has one timer on the oldest outstanding packet

**Decision:** The sender maintains `[base, next_seq)` as the outstanding sequence interval, slides the window as each cumulative ACK advances `base`, and restarts the timer only when `base` moves. On timeout it retransmits the outstanding suffix from `base`.

**Reason:** This is the defining Go-Back-N recovery model. Waiting for the entire window before sending new packets accidentally turns a sliding window into stop-and-wait batches and distorts the comparison.

**Trade-off:** One lost packet can cause retransmission of later packets that were already received out of order.

## D08 - Selective Repeat keeps independent outstanding-packet timers

**Decision:** Maintain timer/retry state only for unacknowledged packets in the active window; remove that state after ACK. Continue checking timers even after invalid/foreign input.

**Reason:** SR can recover an individual missing packet while retaining acknowledged out-of-order packets. Keeping timers for every packet ever sent creates unnecessary work and memory growth.

**Trade-off:** SR requires a buffering receiver and more sender/receiver state than GBN.

## D09 - Keep the receiver import-safe and transactional

**Decision:** Receiver socket binding and receive loops belong in an explicit class or `run()` entry point. Received bytes go to a `.part` file; rename to the final path only after valid END and integrity checks.

**Reason:** Import-time networking prevents unit testing and makes tools accidentally bind ports. Transactional output prevents partial files from looking like completed transfers.

**Trade-off:** The implementation must define and test cleanup behavior for all failure paths and handle the final rename on the target filesystem.

## D10 - Model delay/reordering with a scheduled delivery queue

**Decision:** The proxy uses one time-ordered queue of `(release_time, packet, destination)` and wakes at the next release deadline. Reordering is an extra seeded hold applied to selected packets.

**Reason:** Sleeping inside a single receive loop serializes all traffic and caps packet forwarding rate. A queue preserves the single-threaded design while allowing packets to be released independently of later arrivals.

**Trade-off:** This is a controlled discrete-event approximation, not a real network emulator. It does not model bandwidth caps, correlated loss, queues across a real route, or physical link contention.

## D11 - Isolate random streams by direction and run

**Decision:** Each directional fault injector owns a `random.Random(seed)` instance. Each run receives a deterministic seed derived from a base seed and run identity.

**Reason:** Seeding the global random module makes independent injectors interfere and makes results sensitive to call order elsewhere in the process. Per-injector random streams improve reproducibility.

**Trade-off:** Reproducibility still depends on recording the configuration and keeping the fault-injection call sequence stable between versions.

## D12 - Record configured and realized faults separately

**Decision:** Store requested rates/configuration and actual event counts from the proxy for DATA and ACK directions.

**Reason:** A configured probability is not the observed rate of one finite run. Proxy counters let the analysis describe what actually happened.

**Trade-off:** Small sample runs can deviate substantially from configured probabilities; the results must show packet counts and sample sizes.

## D13 - Isolate every run and retain failures

**Decision:** Each attempt gets a unique run ID, ports, output directory, metrics paths and seed. Every attempted run produces a CSV row, including failures.

**Reason:** Fixed metrics paths prevent safe parallel runs and can cause stale data to be mistaken for current output. Dropping failures inflates apparent reliability and can bias performance summaries.

**Trade-off:** More output files and a wider CSV schema require cleanup policies and stable metadata definitions.

## D14 - Use monotonic high-resolution timing and verified throughput

**Decision:** Use `time.perf_counter()` for elapsed measurements. Define completion time from first DATA send through END ACK. Calculate throughput only when byte count and SHA-256 verification pass.

**Reason:** Wall-clock changes should not affect durations; the completion-time definition must be consistent across protocols. An unverified transfer cannot support a meaningful delivered-throughput claim.

**Trade-off:** Hashing time is reported separately and does not inflate the ARQ completion-time metric.

## D15 - Report median, IQR, and success rate

**Decision:** Use at least five repetitions for standard comparisons and ten for headline experiments; report median and IQR with success rate.

**Reason:** Retransmission timeouts can create skewed completion-time distributions. Mean/std alone can conceal the typical run and failures must remain visible.

**Trade-off:** This increases the number of transfers, but the optimized timeout and tiered runner make the matrix manageable.

## D16 - Keep the project focused on ARQ, not transport replacement

**Decision:** No congestion control, adaptive RTO, bandwidth cap, dissector, or TCP/QUIC benchmark is included in v1.0.

**Reason:** The research questions concern controlled ARQ behavior under loss, delay, duplication, corruption, and reordering. Adding transport-wide mechanisms would introduce variables that make this comparison harder to interpret.

**Trade-off:** Results describe a localhost ARQ testbed only. Use TCP for general reliable byte streams; use QUIC where its stream multiplexing and user-space transport features are required. This prototype is not suitable as a production transport.

## D17 - Make receiver lifecycle explicit and transactional

**Decision:** Keep receiver construction and binding out of module import. Use an injectable `Receiver` class, a bounded idle deadline, a `.part` output, and atomic rename after END and optional source-integrity checks.

**Reason:** A receiver that binds at import cannot be safely unit-tested or imported by tooling. Directly writing to the final path can leave a partial output that looks complete after a sender crash.

**Trade-off:** The receiver handles one transfer per process and requires the runner to provide source size and SHA-256 metadata for its own integrity status to be fully verified.

## D18 - Do not acknowledge data outside the Selective Repeat receive window

**Decision:** ACK SR packets only when they are in `[expected, expected + W)` or are below `expected` and therefore already delivered. Ignore packets at or above the upper boundary.

**Reason:** Acknowledging data that was not buffered can make the sender discard a packet the receiver never accepted. Re-ACKing delivered packets is still necessary when the original ACK was lost.

**Trade-off:** Out-of-window packets wait for the sender's retransmission after the receive window advances.

## D19 - Model delay and reordering with release-time scheduling

**Decision:** Schedule each packet copy in a min-heap by release time. A selected reorder event adds a direction-specific hold to that packet.

**Reason:** A blocking `sleep()` inside the one-thread receive loop prevents unrelated packets from being received or forwarded and invalidates timing comparisons.

**Trade-off:** The queue is a discrete-event approximation and is not a model of real router buffering, congestion, or queue overflow.

## D20 - Give DATA and ACK independent deterministic random streams

**Decision:** Use one `random.Random` instance per direction. DATA uses the run seed; ACK uses a deterministic XOR-derived seed.

**Reason:** Global random state couples otherwise independent injectors and makes tests sensitive to unrelated random calls.

**Trade-off:** A seed reproduces decisions only when the code version and order of injector calls are also fixed and recorded.

## D21 - Count actual reordering separately from configured reorder probability

**Decision:** Record packets selected for a reorder hold and count delivered copies whose arrival order is behind a packet already delivered.

**Reason:** A configured reorder probability does not imply that an actual overtake occurred in a small run. The experiment must distinguish the injection decision from the observed delivery order.

**Trade-off:** Reordering counts refer to datagram copies and delivery order, not necessarily unique DATA sequence numbers. Duplicate copies can therefore affect the raw count and must be interpreted with the duplication counters.

## D22 - Persist proxy statistics periodically and on graceful shutdown

**Decision:** Write stats atomically after a configurable number of observed datagrams and at shutdown. A local shutdown datagram asks the proxy to drain pending deliveries before exit.

**Reason:** A process terminated immediately by the runner may never execute its final statistics dump. Periodic writes preserve intermediate evidence while graceful shutdown preserves the final queue and counter state.

**Trade-off:** More frequent writes add filesystem overhead; the flush interval is configurable and should remain fixed within a benchmark matrix.

## Decision review policy

A decision is revisited only when an implementation defect, test result, experimental finding, or explicit scope change provides evidence. Any change that affects packet format, metric definitions, or experiment comparability must be recorded with its reason and impact before the full benchmark is run.


## Milestone 3 decisions (2026-11-13)

The following decisions were added while implementing the test suite and experimental framework. They complement the M1 and M2 decisions above.

## D23 - Generate deterministic, format-valid transfer fixtures

**Decision:** Keep three seeded text files and generate a valid PNG and WAV using only Python's standard library. Store each fixture's byte count and SHA-256 in `manifest.json`.

**Reason:** The transfer matrix must include text and binary data without adding runtime fixture-download dependencies or checking in hand-edited test data.

**Trade-off:** The generated image/audio are synthetic fixtures, not representative media workloads. Their purpose is byte-integrity and binary-transfer correctness.

## D24 - Synchronize child processes by READY output and isolate run artifacts

**Decision:** Start receiver and proxy with `sys.executable`, wait for explicit READY lines, and assign every run its own output directory, metrics paths, seed and UDP port pair.

**Reason:** Fixed sleeps waste time and are race-prone. Shared metrics filenames and ports prevent safe concurrent execution and can mix stale data into a result.

**Trade-off:** The runner depends on stable READY messages and localhost port allocation; parallel timing workers can still compete for host CPU and are limited to one or two for performance experiments.

## D25 - Freeze one ordered result schema and persist every attempt

**Decision:** Use `experiments/results.py::FIELDS` as the canonical CSV header. Append a row for every attempted run, retain errors and partial process metrics, and reject unrecognized metric names.

**Reason:** The full matrix is expensive; changing column meaning mid-run or omitting failed attempts makes comparisons difficult to reproduce and success rates biased.

**Trade-off:** New fields require a deliberate schema revision and new benchmark series rather than silently modifying a CSV already in use.

## D26 - Treat transfer success as a multi-process integrity condition

**Decision:** A run is successful only when sender, receiver and proxy reports exist, their effective configurations match, receiver completion succeeds, the final output exists, byte counts match, and SHA-256 digests match.

**Reason:** A sender's successful END exchange alone does not prove the receiver published the correct file or that all processes used the intended parameters.

**Trade-off:** A process/report failure makes the run a failed attempt even if some packets were exchanged; partial metrics remain in the CSV for diagnosis.

## D27 - Separate completion timing, data recovery and END retries

**Decision:** Measure with `time.perf_counter()` from first DATA send through END ACK; start with first END send only for an empty file. Count DATA retransmissions, END retries, encoded sender bytes and recovery latency separately.

**Reason:** Mixing END retries into DATA retransmissions or timing the pre-transfer setup obscures the ARQ behavior under study and makes protocol comparisons inconsistent.

**Trade-off:** Receiver hashing and file publication are separate from the sender completion-time interval. Throughput is emitted only for byte/hash-verified success.

## D28 - Retain failures in reliability summaries, not performance distributions

**Decision:** Group all attempts to calculate success rate. Calculate median, Q1, Q3 and IQR for completion time, throughput and DATA retransmissions over verified successes only.

**Reason:** Failed runs must reduce observed reliability, but an undefined throughput or completion time must not be converted to zero or included as if it were a valid measurement.

**Trade-off:** A group with no verified successes has a success rate of zero and no performance distribution; it must be reported as such rather than omitted.

## D29 - Compare fault parameters and observed events with explicit units

**Decision:** Report configured probabilities separately from realized per-direction event rates; report fixed delay in seconds and observed delayed-packet fraction as separate, labelled quantities. Keep scheduled reorder holds separate from actual overtaking deliveries.

**Reason:** A finite sample will not generally realize its configured probability exactly. Delay is a duration, not a probability, and a scheduled reorder hold does not guarantee actual overtaking.

**Trade-off:** The fault comparison output is not a single unitless deviation score for every fault. Readers must interpret each parameter alongside its unit, event denominator and raw counter.

## D30 - Keep the full matrix out of pytest and limit timing concurrency

**Decision:** Keep smoke/quick/full experiment tiers separate from pytest; fast pytest includes three real process-level transfers. Default to one worker and recommend one or two for timing matrices.

**Reason:** Tests should be repeatable and quick enough for every commit, while a 905-attempt research run is an explicit experiment. Parallel CPU contention would compromise latency comparisons.

**Trade-off:** CI's smoke tier validates a small subset, not the entire research question matrix. The full suite must be run as a separate pre-release action.

## D31 - Generate plots only from verified rows and preserve a manifest

**Decision:** Performance plots consume byte/hash-verified rows only; combined-fault success-rate plots count all attempts. The plotting command writes a manifest of generated plot names and the source CSV label.

**Reason:** A plot should not imply delivered throughput for a failed transfer or silently change its sample set. The manifest makes a partial matrix's available figures explicit.

**Trade-off:** Not every figure exists after every tier; a plot is generated only when the corresponding input matrix contains usable observations.


## Milestone 4 — Evidence and release decisions

## D32 - Do not promote smoke observations into research conclusions

**Decision:** Label the six-transfer smoke dataset as a correctness/instrumentation check. Keep RQ1–RQ6 inconclusive until the full pre-registered matrix is run.

**Reason:** A single observation per protocol/condition cannot support median/IQR estimates or reliable comparisons. The smoke tier does not exercise all fault types or file classes.

**Trade-off:** The project can be packaged as a release candidate, but a final v1.0 performance claim must wait for the full benchmark.

## D33 - Keep the full matrix definition immutable during execution

**Decision:** Freeze the 905-attempt task list, seed derivation, fault settings, timing parameters, and CSV field order before the final run. Any schema/method change creates a new experiment series and is documented.

**Reason:** Changing conditions while the matrix is running would break matched comparisons and make the result difficult to reproduce.

**Trade-off:** A discovered experimental-design defect must be fixed before starting a fresh full run rather than patched silently into partial results.

## D34 - Separate release preparation from release publication

**Decision:** Prepare the license, changelog, repository metadata, release checklist and demo storyboard in the source repository. Create the actual GitHub tag/release only after the benchmark, demo recording and clean-checkout checks pass.

**Reason:** A source ZIP and release notes do not prove that the published repository meets its Definition of Done.

**Trade-off:** The deliverable is described as a release candidate until the external recording and publication steps are actually completed.
