# Conclave

Governance Control Plane for Federated Learning.

## Getting Started

### Installation

To run Conclave locally during development, set up the virtual environment and install the package in editable mode:

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -e .
```

### Usage

Run the CLI:

```bash
conclave
```

### Real thesis workload: CIFAR-10 with ResNet-18

Create a training session with `--dataset cifar10`. Conclave selects a
CIFAR-10-adapted ResNet-18 and creates deterministic Dirichlet non-IID client
partitions (default alpha = 0.5). Each participating node downloads the
public CIFAR-10 dataset into its own `~/.conclave/data` cache (or
`CONCLAVE_DATA_DIR`) on first use; later runs use that local cache. For a CPU-only demonstration, use a small number of
rounds, for example `rounds=1` in the session description.

### Threshold Secure Aggregation

Secure-aggregation rounds use ephemeral X25519 pairwise masks. The local Flower
orchestrator also creates Shamir recovery shares for each client key. When a
client drops out, the configured threshold of surviving peers can reconstruct
that dropped key and cancel its unmatched masks, without releasing active
clients' keys. The recovery primitive is implemented in
`conclave.integrations.flower.threshold_secagg` and is covered by unit tests.
