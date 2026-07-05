# Walkthrough - Privacy & Security Overhead Analysis Benchmark

We have implemented and verified the benchmark measuring the overhead introduced by Conclave's privacy-preserving features (Secure Aggregation and Differential Privacy) over 5 runs with **5 nodes** and a **100,000 parameters** model size.

## Benchmark Design & Implementation

The complete implementation is in [benchmark_security_overhead.py](file:///d:/conclave_v1/benchmarks/benchmark_security_overhead.py). Key features include:
1. **Four Evaluated Security Configurations**:
   - **Configuration A (Plain)**: Plain FedAvg (No SecAgg masking, no DP noise).
   - **Configuration B (SecAgg)**: FedAvg + Secure Aggregation (no DP noise).
   - **Configuration C (DP)**: FedAvg + Differential Privacy (no SecAgg masking).
   - **Configuration D (SecAgg + DP)**: Both Secure Aggregation and Differential Privacy enabled.
2. **Sub-millisecond Precision**: Uses `time.perf_counter()` to record timing of masking, serialization, averaging, and DP noise generation phases.
3. **Robust Metrics Averaging**: Calculates average values for all timing, CPU, and memory metrics over 5 sequential repetitions of each configuration.
4. **Communication Payload Size**: Calculates the total serialized parameters (in bytes) transmitted by all 5 clients.

---

## Benchmark Run Summary

The benchmark was executed successfully. Below is the recorded metrics data:

| Configuration | Total Round (ms) | Aggregation (ms) | Secure Aggregation (ms) | DP Noise (ms) | Payload Size (bytes) | CPU Usage (%) | Peak Memory (MB) |
|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| **A (Plain)** | 4.744 | 0.852 | 0.000 | 0.000 | 2,000,000 | 0.00% | 38.3 |
| **B (SecAgg)** | 11.673 | 2.942 | 4.831 | 0.000 | 2,000,000 | 12.18% | 41.4 |
| **C (DP)** | 6.142 | 0.810 | 0.000 | 2.358 | 2,000,000 | 0.00% | 38.5 |
| **D (SecAgg+DP)** | 16.504 | 3.305 | 4.612 | 4.778 | 2,000,000 | 18.15% | 42.2 |

### Observations
- **Secure Aggregation Cost**: Enabling Secure Aggregation (Config B) increases the total round duration from $4.74\text{ ms}$ to $11.67\text{ ms}$ ($\sim 146\%$ overhead increase). This is due to the computation involved in generating and applying pairwise normal masks across 5 nodes.
- **Differential Privacy Cost**: Adding Differential Privacy noise (Config C) introduces a small overhead ($2.36\text{ ms}$ noise generation time), resulting in a $6.14\text{ ms}$ round duration.
- **Combined Impact**: Enabling both SecAgg and DP (Config D) results in the highest round duration ($16.50\text{ ms}$), reflecting the additive nature of the security mechanisms.
- **Payload Stability**: The communication payload size is identical ($2,000,000$ bytes) across all configurations, confirming that masking and noise generation do not expand model parameter dimensions.
- **Resource Footprint**: Average CPU usage scales from $0\%$ to $18.15\%$, and peak memory remains extremely low ($38.3\text{ MB}$ to $42.2\text{ MB}$).

---

## Output Verification

The output files are generated and verified:
1. **CSV Log File**: Located at [security_overhead.csv](file:///d:/conclave_v1/results/security_overhead.csv).
2. **Total FL Round Duration Graph**:
   - [security_overhead_total.png](file:///d:/conclave_v1/figures/security_overhead_total.png) (300 DPI)
   - [security_overhead_total.svg](file:///d:/conclave_v1/figures/security_overhead_total.svg)
   - [security_overhead_total.pdf](file:///d:/conclave_v1/figures/security_overhead_total.pdf)
3. **Aggregation Duration Graph**:
   - [security_overhead_aggregation.png](file:///d:/conclave_v1/figures/security_overhead_aggregation.png) (300 DPI)
   - [security_overhead_aggregation.svg](file:///d:/conclave_v1/figures/security_overhead_aggregation.svg)
   - [security_overhead_aggregation.pdf](file:///d:/conclave_v1/figures/security_overhead_aggregation.pdf)
4. **Communication Payload Graph**:
   - [security_overhead_payload.png](file:///d:/conclave_v1/figures/security_overhead_payload.png) (300 DPI)
   - [security_overhead_payload.svg](file:///d:/conclave_v1/figures/security_overhead_payload.svg)
   - [security_overhead_payload.pdf](file:///d:/conclave_v1/figures/security_overhead_payload.pdf)
5. **CPU Usage Graph**:
   - [security_overhead_cpu.png](file:///d:/conclave_v1/figures/security_overhead_cpu.png) (300 DPI)
   - [security_overhead_cpu.svg](file:///d:/conclave_v1/figures/security_overhead_cpu.svg)
   - [security_overhead_cpu.pdf](file:///d:/conclave_v1/figures/security_overhead_cpu.pdf)
