# Walkthrough - Cryptographic Audit Ledger Scalability Benchmark

We have implemented and verified the scalability benchmark measuring the performance and integrity validation of Conclave's cryptographic audit ledger (SHA-256 hash chain) across sizes $C \in \{500, 5\,000, 10\,000, 25\,000, 50\,000\}$ entries over 5 runs.

## Benchmark Design & Implementation

The complete implementation is in [benchmark_audit_ledger.py](file:///d:/conclave_v1/benchmarks/benchmark_audit_ledger.py). Key features include:
1. **Accurate SHA-256 Chaining**: Implements the identical hash chaining algorithm utilized in Conclave production. Each record contains realistic fields (event ID, timestamp, event type, resource type, resource name, action, status, message, and previous hash) and hashes them together with the preceding block's hash.
2. **Sub-millisecond Performance Timings**: Measures append time and verification time using `time.perf_counter()`.
3. **Integrity Validation Tampering Test**: After each benchmark iteration, a random index in the chain is corrupted. The verification process is run to confirm that tampering is successfully detected, capture the corruption detection latency, and restore the original block.
4. **Memory Footprint Tracking**: Tracks peak process Resident Set Size (RSS) during execution.

---

## Benchmark Run Summary

The benchmark was executed successfully. Below is the recorded metrics data:

| Chain Size | Append Time (ms) | Append (logs/sec) | Verify Time (ms) | Verify (logs/sec) | Peak Memory (MB) | Tamper Detected? | Corruption Latency (ms) |
|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| 500 | 2.900 | 172,944.4 | 0.996 | 502,670.3 | 37.7 | True | 0.373 |
| 5,000 | 29.942 | 167,173.9 | 10.361 | 482,745.0 | 40.1 | True | 4.535 |
| 10,000 | 67.824 | 152,641.4 | 22.067 | 462,389.8 | 42.8 | True | 7.760 |
| 25,000 | 152.289 | 164,256.0 | 52.457 | 477,404.5 | 51.2 | True | 23.496 |
| 50,000 | 312.397 | 160,170.7 | 107.581 | 465,800.1 | 65.4 | True | 59.926 |

### Observations
- **Append Performance**: Appending logs scales linearly. We can insert ~160,000 entries per second. 50,000 records append in just $312.4\text{ ms}$.
- **Verification Throughput**: Chain verification is extremely fast, validating around ~460,000 logs per second. Checking 50,000 entries takes only $107.6\text{ ms}$.
- **Tamper Detection Latency**: Tamper detection is instantaneous. Because we stop validation immediately upon discovering a hash mismatch, the detection latency is proportional to the position of the tampered block in the chain, averaging $59.9\text{ ms}$ for a chain of 50,000 records.
- **Memory Overhead**: Memory scaling is highly conservative, requiring only $65.4\text{ MB}$ to hold all 50,000 linked records in memory.

---

## Output Verification

The output files are generated and verified:
1. **CSV Log File**: Located at [audit_ledger_scalability.csv](file:///d:/conclave_v1/results/audit_ledger_scalability.csv).
2. **Append Throughput Graph**:
   - [audit_ledger_append_throughput.png](file:///d:/conclave_v1/figures/audit_ledger_append_throughput.png) (300 DPI)
   - [audit_ledger_append_throughput.svg](file:///d:/conclave_v1/figures/audit_ledger_append_throughput.svg)
   - [audit_ledger_append_throughput.pdf](file:///d:/conclave_v1/figures/audit_ledger_append_throughput.pdf)
3. **Verification Duration Graph**:
   - [audit_ledger_verification_time.png](file:///d:/conclave_v1/figures/audit_ledger_verification_time.png) (300 DPI)
   - [audit_ledger_verification_time.svg](file:///d:/conclave_v1/figures/audit_ledger_verification_time.svg)
   - [audit_ledger_verification_time.pdf](file:///d:/conclave_v1/figures/audit_ledger_verification_time.pdf)
4. **Verification Throughput Graph**:
   - [audit_ledger_verification_throughput.png](file:///d:/conclave_v1/figures/audit_ledger_verification_throughput.png) (300 DPI)
   - [audit_ledger_verification_throughput.svg](file:///d:/conclave_v1/figures/audit_ledger_verification_throughput.svg)
   - [audit_ledger_verification_throughput.pdf](file:///d:/conclave_v1/figures/audit_ledger_verification_throughput.pdf)
5. **Peak Memory Usage Graph**:
   - [audit_ledger_memory_usage.png](file:///d:/conclave_v1/figures/audit_ledger_memory_usage.png) (300 DPI)
   - [audit_ledger_memory_usage.svg](file:///d:/conclave_v1/figures/audit_ledger_memory_usage.svg)
   - [audit_ledger_memory_usage.pdf](file:///d:/conclave_v1/figures/audit_ledger_memory_usage.pdf)
