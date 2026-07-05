# Walkthrough - Metrics Database Ingestion Throughput Benchmark

We have implemented and verified the scalability benchmark measuring the write performance and concurrency threshold of Conclave's metrics database under workloads of $T \in \{1, 5, 10, 20, 50\}$ writer threads, each sequentially inserting 1,000 metrics records.

## Benchmark Design & Implementation

The complete implementation is in [benchmark_metrics_db.py](file:///d:/conclave_v1/benchmarks/benchmark_metrics_db.py). Key features include:
1. **Accurate Data Ingestion Simulation**: Simulates the exact telemetry payload (timestamp, node_id, cpu, ram, gpu, disk, network_sent, network_rec, and heartbeat status) sent by nodes during training.
2. **Concurrent Write Handling**: Spawns concurrent thread objects, each holding its own independent SQLite connection and executing sequential writes one-by-one.
3. **SQLite Optimizations**: To bypass SQLite's standard single-writer lock bottlenecks, connections are set to **Write-Ahead Logging (WAL)** mode (`PRAGMA journal_mode=WAL;`), synchronous operations are set to normal (`PRAGMA synchronous=NORMAL;`), and a connection busy timeout of 30 seconds is applied.
4. **Post-Benchmark Integrity Validation**: Confirms successful ingestion counts, checks duplicate primary keys, and verifies database readability after each run.

---

## Benchmark Run Summary

The benchmark was executed successfully. Below is the recorded metrics data:

| Threads | Total Ops | Success writes | Failed writes | Execution Time (ms) | Avg Latency (ms) | Throughput (writes/sec) | DB Size (MB) | Peak Memory (MB) | CPU Usage (%) |
|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| 1 | 1,000 | 1,000 | 0 | 54.9 | 0.047 | 18,243.2 | 0.11 | 39.0 | 7.74 |
| 5 | 5,000 | 5,000 | 0 | 276.9 | 0.173 | 18,152.1 | 0.49 | 40.8 | 8.13 |
| 10 | 10,000 | 10,000 | 0 | 626.1 | 0.324 | 16,115.8 | 0.96 | 41.8 | 8.71 |
| 20 | 20,000 | 20,000 | 0 | 1,289.9 | 0.680 | 15,537.6 | 1.92 | 44.4 | 8.39 |
| 50 | 50,000 | 50,000 | 0 | 3,219.8 | 1.690 | 15,674.8 | 4.85 | 52.7 | 8.35 |

### Observations
- **High Ingestion Performance**: Due to our WAL and NORMAL optimizations, SQLite performs remarkably well, achieving **~15,000 to ~18,000 writes/sec** even with 50 threads writing simultaneously.
- **Reliable Thread Concurrency**: We achieved **0 failed writes** across all configurations. The 30s busy timeout and WAL database mode completely mitigated write lock collisions.
- **Latency Scaling**: Average single-write latency scales linearly with thread count ($0.047\text{ ms}$ for 1 thread to $1.69\text{ ms}$ for 50 threads), representing the queuing delays as threads wait for access to write to the database file.
- **Database Footprint**: SQLite database storage overhead scales linearly, taking only $4.85\text{ MB}$ to store 50,000 records.
- **Compute Efficiency**: CPU usage remains flat at ~8%, and peak memory usage scales conservatively to $52.7\text{ MB}$.

---

## Output Verification

The output files are generated and verified:
1. **CSV Log File**: Located at [metrics_db_benchmark.csv](file:///d:/conclave_v1/results/metrics_db_benchmark.csv).
2. **Ingestion Throughput Graph**:
   - [metrics_db_throughput.png](file:///d:/conclave_v1/figures/metrics_db_throughput.png) (300 DPI)
   - [metrics_db_throughput.svg](file:///d:/conclave_v1/figures/metrics_db_throughput.svg)
   - [metrics_db_throughput.pdf](file:///d:/conclave_v1/figures/metrics_db_throughput.pdf)
3. **Average Write Latency Graph**:
   - [metrics_db_latency.png](file:///d:/conclave_v1/figures/metrics_db_latency.png) (300 DPI)
   - [metrics_db_latency.svg](file:///d:/conclave_v1/figures/metrics_db_latency.svg)
   - [metrics_db_latency.pdf](file:///d:/conclave_v1/figures/metrics_db_latency.pdf)
4. **Database File Size Graph**:
   - [metrics_db_size.png](file:///d:/conclave_v1/figures/metrics_db_size.png) (300 DPI)
   - [metrics_db_size.svg](file:///d:/conclave_v1/figures/metrics_db_size.svg)
   - [metrics_db_size.pdf](file:///d:/conclave_v1/figures/metrics_db_size.pdf)
5. **CPU Utilization Graph**:
   - [metrics_db_cpu.png](file:///d:/conclave_v1/figures/metrics_db_cpu.png) (300 DPI)
   - [metrics_db_cpu.svg](file:///d:/conclave_v1/figures/metrics_db_cpu.svg)
   - [metrics_db_cpu.pdf](file:///d:/conclave_v1/figures/metrics_db_cpu.pdf)
