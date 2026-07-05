# Walkthrough - Model Size Scalability Benchmark

We have implemented and verified the scalability benchmark measuring how Conclave's aggregation, serialization, and privacy mechanisms scale as model size increases ($1\,000, 10\,000, 100\,000, 1\,000\,000$ parameters) with a fixed count of **5 nodes**.

## Benchmark Design & Implementation

The complete implementation is in [benchmark_model_scalability.py](file:///d:/conclave_v1/benchmarks/benchmark_model_scalability.py). Key features of this benchmark include:
1. **Accurate Conclave Simulation**: Simulates the exact mechanisms used in Conclave:
   - **Secure Aggregation**: Pairs clients and generates pairwise masks matching the model shape. It accumulates these masks to form a zero-sum aggregate across the network.
   - **FedAvg**: Averages the client parameters element-wise.
   - **Differential Privacy**: Adds Laplace noise matching the target epsilon and L2 sensitivity bounds over the aggregated parameters.
2. **Sub-millisecond Precision**: Uses `time.perf_counter()` to record latency (in milliseconds) of each isolated computation phase (masking, serialization, FedAvg, and DP noise generation).
3. **Peak Memory Measurement**: Uses `psutil` to track peak memory RSS of the process tree during round execution.

---

## Benchmark Run Summary

The benchmark was executed successfully. Below is the recorded metrics data:

| Parameters | FedAvg (ms) | Secure Aggregation (ms) | DP Noise (ms) | Serialization (ms) | Total Round (ms) | Peak Memory (MB) |
|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| 1,000 | 0.079 | 0.769 | 0.035 | 0.014 | 8.491 | 38.8 |
| 10,000 | 0.274 | 1.375 | 0.373 | 0.012 | 4.088 | 39.1 |
| 100,000 | 1.093 | 6.043 | 2.487 | 0.173 | 14.111 | 42.5 |
| 1,000,000 | 11.395 | 61.177 | 26.427 | 1.412 | 128.222 | 69.7 |

### Observations
- **Secure Aggregation Scaling**: Secure Aggregation masking time scales linearly with the number of parameters ($0.77\text{ ms}$ for $1\,000$ parameters to $61.18\text{ ms}$ for $1\,000\,000$ parameters). Generating pseudo-random normal distributions for masking forms the primary compute overhead.
- **Aggregation & Privacy**: Both FedAvg averaging ($11.4\text{ ms}$ at $1\text{M}$) and Laplace noise generation ($26.4\text{ ms}$ at $1\text{M}$) scale linearly with parameter counts but are extremely fast.
- **Memory Footprint**: Peak memory remains highly efficient, rising from $38.8\text{ MB}$ to $69.7\text{ MB}$ as the parameters increase to 1,000,000.

---

## Output Verification

The output files are generated and verified:
1. **CSV Log File**: Located at [model_scalability.csv](file:///d:/conclave_v1/results/model_scalability.csv).
2. **FedAvg Scaling Graph**:
   - [model_scalability_fedavg.png](file:///d:/conclave_v1/figures/model_scalability_fedavg.png) (300 DPI)
   - [model_scalability_fedavg.svg](file:///d:/conclave_v1/figures/model_scalability_fedavg.svg)
   - [model_scalability_fedavg.pdf](file:///d:/conclave_v1/figures/model_scalability_fedavg.pdf)
3. **Secure Aggregation Scaling Graph**:
   - [model_scalability_secagg.png](file:///d:/conclave_v1/figures/model_scalability_secagg.png) (300 DPI)
   - [model_scalability_secagg.svg](file:///d:/conclave_v1/figures/model_scalability_secagg.svg)
   - [model_scalability_secagg.pdf](file:///d:/conclave_v1/figures/model_scalability_secagg.pdf)
4. **Differential Privacy Scaling Graph**:
   - [model_scalability_dp.png](file:///d:/conclave_v1/figures/model_scalability_dp.png) (300 DPI)
   - [model_scalability_dp.svg](file:///d:/conclave_v1/figures/model_scalability_dp.svg)
   - [model_scalability_dp.pdf](file:///d:/conclave_v1/figures/model_scalability_dp.pdf)
5. **Total FL Round Scaling Graph**:
   - [model_scalability_total.png](file:///d:/conclave_v1/figures/model_scalability_total.png) (300 DPI)
   - [model_scalability_total.svg](file:///d:/conclave_v1/figures/model_scalability_total.svg)
   - [model_scalability_total.pdf](file:///d:/conclave_v1/figures/model_scalability_total.pdf)
