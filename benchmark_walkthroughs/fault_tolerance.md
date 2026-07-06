# Walkthrough - Fault Tolerance & System Resilience Benchmark

We have implemented and verified the scalability benchmark measuring Conclave's ability to detect, tolerate, and recover from failures during federated learning across 5 independent scenarios, repeated 5 times.

## Benchmark Design & Implementation

The complete implementation is in [benchmark_fault_tolerance.py](file:///d:/conclave_v1/benchmarks/benchmark_fault_tolerance.py). Key features include:
1. **Configurable Heartbeat Timeout**: Patched `_transition_if_offline` in [services.py](file:///d:/conclave_v1/src/conclave/server/services.py) to read the `CONCLAVE_HEARTBEAT_TIMEOUT` environment variable (default 120s), configuring it to 2.0s during tests to speed up missed heartbeat detection.
2. **Auto Node Offline Auditing**: Modified `_transition_if_offline` to write a `NODE_DROPPED_OFFLINE` audit event dynamically when status transitions to Offline. This ensures auditing occurs for all node timeouts.
3. **Database File Isolation**: Uses distinct SQLite database file names for every scenario repetition, preventing file locking conflicts and database constraints duplication errors.
4. **Crash Injection**: Simulates node failure mid-training by raising a RuntimeError inside the Flower `fit` method on Round 2, terminating its heartbeat loop.
5. **Ledger Tampering**: Stop the server, edits one row's message directly in the SQLite database, starts the server, and triggers `/audit/verify`.

---

## Benchmark Run Summary

The benchmark was executed successfully. Below is the recorded metrics data:

| Scenario | Failure Detected? | Detection Latency (ms) | Recovery Time (ms) | Training Completed? | Audit Logged? | System Crashed? |
|:---|:---:|:---:|:---:|:---:|:---:|:---:|
| **Node Failure During Training** | Yes | 801.49 | 474.22 | Yes | Yes | No |
| **Missed Heartbeats** | Yes | 1997.08 | 9.33 | No | Yes | No |
| **Invalid Client Certificate** | Yes | 17.16 | 0.00 | No | Yes | No |
| **Tampered Audit Ledger** | Yes | 51.45 | 0.00 | No | Yes | No |
| **Slow Node** | No | 0.00 | 0.00 | Yes | Yes | No |

---

## Output Verification

The output files are generated and verified:
1. **CSV Log File**: Located at [fault_tolerance.csv](file:///d:/conclave_v1/results/fault_tolerance.csv).
2. **Detection Latency Graph**:
   - [fault_tolerance_detection_latency.png](file:///d:/conclave_v1/figures/fault_tolerance_detection_latency.png) (300 DPI)
   - [fault_tolerance_detection_latency.svg](file:///d:/conclave_v1/figures/fault_tolerance_detection_latency.svg)
   - [fault_tolerance_detection_latency.pdf](file:///d:/conclave_v1/figures/fault_tolerance_detection_latency.pdf)
3. **Recovery Time Graph**:
   - [fault_tolerance_recovery_time.png](file:///d:/conclave_v1/figures/fault_tolerance_recovery_time.png) (300 DPI)
   - [fault_tolerance_recovery_time.svg](file:///d:/conclave_v1/figures/fault_tolerance_recovery_time.svg)
   - [fault_tolerance_recovery_time.pdf](file:///d:/conclave_v1/figures/fault_tolerance_recovery_time.pdf)
4. **Training Success Rate Graph**:
   - [fault_tolerance_success_rate.png](file:///d:/conclave_v1/figures/fault_tolerance_success_rate.png) (300 DPI)
   - [fault_tolerance_success_rate.svg](file:///d:/conclave_v1/figures/fault_tolerance_success_rate.svg)
   - [fault_tolerance_success_rate.pdf](file:///d:/conclave_v1/figures/fault_tolerance_success_rate.pdf)
