# Walkthrough - Simulated Hospital Node Scalability Benchmark

We have implemented and verified the scalability benchmark measuring Conclave's performance with varying simulated hospital node counts ($1, 3, 5, 10, 20$).

## Benchmark Implementation

The complete implementation is in [benchmark_node_scalability.py](file:///d:/conclave_v1/benchmarks/benchmark_node_scalability.py). Key features of the benchmark script include:
1. **Database & Port Isolation**: For each node scale $N$, a fresh Conclave FastAPI server is started in a background subprocess on port `8000 + N` using a temporary isolated SQLite database file.
2. **SQLite WAL Optimization**: Programmatically sets the SQLite database to **Write-Ahead Logging (WAL)** mode. This ensures high concurrency and prevents write collisions (`database is locked` errors) when registering, approving, and heartbeating $20$ nodes simultaneously.
3. **Cryptographic Identity Management**: Programmatically generates distinct RSA-2048 key pairs for all simulated nodes, registers them via the `/nodes/register` endpoint, and approves them using the `/nodes/approve/{node_id}` endpoint.
4. **Heartbeat Simulation**: Spawns concurrent daemon threads for the nodes. Each node signs periodic heartbeats using its private RSA key and a JWT payload, reporting system utilization metrics to `/nodes/heartbeat/{node_id}`.
5. **Flower Client Orchestration**: Once a node detects an `active_task` in its heartbeat response, it launches a Flower client thread that connects to the server and participates in 3 rounds of training, returning dummy weights.
6. **Platform Bug Fix**: Resolved a critical coordinator bug in [orchestrator.py](file:///d:/conclave_v1/src/conclave/integrations/flower/orchestrator.py) where the Flower server process startup was assumed to have failed if it exited with code 0 (clean completion) within the first 2 seconds.
7. **Robust Resource Monitoring**: We implemented an accumulated CPU time delta calculation method. By tracking user/system CPU seconds over the process tree (main process + uvicorn server + Flower subprocesses) and dividing by duration and cores, we get highly accurate, non-zero CPU metrics.

---

## Benchmark Run Summary

The benchmark was executed successfully. Below is the recorded metrics data:

| Nodes | Total Runtime (sec) | Avg Heartbeat Latency (ms) | Avg Round Duration (sec) | Total Heartbeats | CPU Usage (%) | Peak Memory (MB) |
|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| 1 | 5.88 | 10.17 | 1.00 | 3 | 6.9% | 310.8 |
| 3 | 5.55 | 36.18 | 0.79 | 6 | 6.8% | 313.8 |
| 5 | 5.83 | 30.51 | 0.79 | 10 | 5.6% | 316.9 |
| 10 | 6.78 | 47.17 | 0.85 | 30 | 7.8% | 323.4 |
| 20 | 8.07 | 63.78 | 0.93 | 60 | 7.5% | 336.9 |

### Observations
- **Runtime Scalability**: Total runtime scales very gracefully, starting at ~5.88s for 1 node and only increasing to 8.07s for 20 concurrent nodes.
- **Heartbeat Latency**: Average heartbeat request round-trip latency increases from ~10ms at low node counts to ~64ms for 20 nodes due to increased endpoint request volume.
- **Memory Overhead**: Memory utilization scales linearly and conservatively, keeping peak memory under 337 MB across all 20 nodes and 2 server processes.

---

## Output Verification

The output files are generated and verified:
1. **CSV Log File**: Located at [node_scalability.csv](file:///d:/conclave_v1/results/node_scalability.csv).
2. **Runtime Graph**: Saved in three formats:
   - [node_runtime.png](file:///d:/conclave_v1/figures/node_runtime.png) (300 DPI)
   - [node_runtime.svg](file:///d:/conclave_v1/figures/node_runtime.svg)
   - [node_runtime.pdf](file:///d:/conclave_v1/figures/node_runtime.pdf)
3. **Heartbeat Latency Graph**: Saved in three formats:
   - [heartbeat_latency.png](file:///d:/conclave_v1/figures/heartbeat_latency.png) (300 DPI)
   - [heartbeat_latency.svg](file:///d:/conclave_v1/figures/heartbeat_latency.svg)
   - [heartbeat_latency.pdf](file:///d:/conclave_v1/figures/heartbeat_latency.pdf)
