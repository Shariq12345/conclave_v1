# Walkthrough - Baseline FL vs. Conclave Comparative Evaluation

We have implemented and verified the comparative benchmark quantifying Conclave's security overhead and architectural tradeoffs.

## Benchmark Design & Implementation

The implementation is located at [benchmark_comparison.py](file:///d:/conclave_v1/benchmarks/benchmark_comparison.py).
1. **Baseline System**: Runs a pure Flower server and 5 client threads. Clients train on a raw numpy array of 100,000 float32 parameters, transmitting parameters over plain HTTP, utilizing raw `FedAvg` (average vector update), and bypassing JWT authentication, heartbeats, database logging, or differential privacy noise.
2. **Conclave System**: Runs the complete Conclave stack—Uvicorn server, 3 database client organizations, 5 node heartbeat tasks, policy authorization checks, Secure Aggregation masking, and Differential Privacy Laplace noise.
3. **Execution Settings**: Both systems execute 5 federated learning rounds with 100,000 parameters over 5 repetitions to compute averaged statistics.

---

## Comparison Summary

Below is the recorded metrics data:

| Metric | Baseline FL | Conclave | Overhead / Difference |
|:---|:---:|:---:|:---|
| **Total Runtime (sec)** | 2.60 | 5.56 | $+2.96\text{ sec}$ ($\approx 2.1\times$ execution duration) |
| **Avg FL Round Duration (sec)** | 0.52 | 1.11 | $+0.59\text{ sec}$ round latency |
| **Avg Aggregation Time (ms)** | 0.15 | 11.01 | $+10.86\text{ ms}$ (due to DP Laplace noise + pairwise masking sum) |
| **Average Heartbeat Latency (ms)** | 0.00 | 38.54 | Conclave heartbeat JWT checking cost |
| **Average CPU Utilization (%)** | 16.88% | 8.01% | Conclave's subprocess isolation leads to lower aggregated core utilization |
| **Peak Memory Footprint (MB)** | 212.0 | 372.6 | $+160.6\text{ MB}$ (FastAPI, Alembic, SQLite connections, security contexts) |
| **Total Network Payload (KB)** | 19,531.2 | 19,606.2 | $+75.0\text{ KB}$ ($\approx 0.38\%$ increase due to heartbeats and REST metadata) |

---

## Security Feature Support Matrix

| Feature / Protocol | Baseline FL | Conclave |
|:---|:---:|:---:|
| **Mutual TLS Communication** | No | **Yes** |
| **Secure Aggregation Masking** | No | **Yes** |
| **Differential Privacy Protection** | No | **Yes** |
| **Cryptographic Hash Chain Audit Ledger** | No | **Yes** |
| **Dynamic Policy Enforcement** | No | **Yes** |
| **Telemetry Metrics Database Ingestion** | No | **Yes** |
| **Certificate-based Node Authentication** | No | **Yes** |
| **Block-level Ledger Tamper Detection** | No | **Yes** |

---

## Output Verification

The output files are generated and verified:
1. **CSV Log File**: Located at [baseline_comparison.csv](file:///d:/conclave_v1/results/baseline_comparison.csv).
2. **Runtime Comparison Chart**:
   - [baseline_comparison_runtime.png](file:///d:/conclave_v1/figures/baseline_comparison_runtime.png) (300 DPI)
   - [baseline_comparison_runtime.svg](file:///d:/conclave_v1/figures/baseline_comparison_runtime.svg)
   - [baseline_comparison_runtime.pdf](file:///d:/conclave_v1/figures/baseline_comparison_runtime.pdf)
3. **CPU Usage Comparison Chart**:
   - [baseline_comparison_cpu.png](file:///d:/conclave_v1/figures/baseline_comparison_cpu.png) (300 DPI)
   - [baseline_comparison_cpu.svg](file:///d:/conclave_v1/figures/baseline_comparison_cpu.svg)
   - [baseline_comparison_cpu.pdf](file:///d:/conclave_v1/figures/baseline_comparison_cpu.pdf)
4. **Memory Footprint Comparison Chart**:
   - [baseline_comparison_memory.png](file:///d:/conclave_v1/figures/baseline_comparison_memory.png) (300 DPI)
   - [baseline_comparison_memory.svg](file:///d:/conclave_v1/figures/baseline_comparison_memory.svg)
   - [baseline_comparison_memory.pdf](file:///d:/conclave_v1/figures/baseline_comparison_memory.pdf)
5. **Network Payload Comparison Chart**:
   - [baseline_comparison_payload.png](file:///d:/conclave_v1/figures/baseline_comparison_payload.png) (300 DPI)
   - [baseline_comparison_payload.svg](file:///d:/conclave_v1/figures/baseline_comparison_payload.svg)
   - [baseline_comparison_payload.pdf](file:///d:/conclave_v1/figures/baseline_comparison_payload.pdf)
