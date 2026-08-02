# Conclave: FedGuard Governance Control Plane for Enterprise Federated Learning

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python: 3.12](https://img.shields.io/badge/Python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![PyTorch: 2.2](https://img.shields.io/badge/PyTorch-2.2-ee4c2c.svg)](https://pytorch.org/)
[![Paper: IEEE Transactions](https://img.shields.io/badge/IEEE%20Transactions-TDSC-00629B.svg)](research_paper/main.pdf)
[![Code Style: Black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

> **Conclave** is the production-grade reference implementation of **FedGuard**, a policy-driven governance control plane for Federated Learning (FL). FedGuard bridges the critical gap between distributed machine learning execution and statutory regulatory compliance (e.g., U.S. HIPAA \S164.312, EU GDPR Articles 5, 7, 17, and 32).

---

## 🌟 Executive Overview

Federated Learning enables multi-institutional collaborative training without raw data centralization. However, enterprise adoption in healthcare and finance is severely hindered by three fundamental challenges:
1. **Lack of Verifiable Governance & Compliance:** Existing FL frameworks (e.g., Flower, FLARE, FATE) focus on execution efficiency, leaving client identity attestation, policy validation, and regulatory enforcement to ad-hoc scripts.
2. **Privacy vs. Robustness Trade-off:** Cryptographic Secure Aggregation (SecAgg) masks client update tensors, preventing aggregators from inspecting individual gradients to apply coordinate-wise Byzantine-robust filters (e.g., Trimmed Mean, Median, Krum).
3. **Regulatory Mandates & Right to Erasure:** Statutory requirements such as GDPR Article 17 (Right to Erasure) require revoking client data influence from trained global models without re-training from scratch.

**FedGuard** decouples governance control from ML execution into an independent control plane $\mathcal{G}$ that manages participant authorization, hardware attestation, privacy budget tracking, Byzantine resilience, machine unlearning, and SHA-256 audit logging.

---

## 🚀 Key Features

* 🔐 **Threshold Secure Aggregation (SecAgg):** Pairwise X25519 Elliptic Curve Diffie-Hellman (ECDH) key agreement coupled with Shamir's $(k, N)$ Secret Sharing over finite Galois Field $\mathbb{F}_q$ ($q = 2^{32}+15$). Enables $k$-of-$N$ surviving nodes to reconstruct dropped clients' pairwise masks without releasing active clients' private keys.
* 🛡️ **Formal Privacy Accounting (R\'enyi Differential Privacy):** Bounded gradient $L_2$ norm clipping ($C = 1.0$), Gaussian noise injection ($\sigma = 0.85$), and exact RDP composition tracked per organization to enforce privacy budget caps ($\epsilon_{\text{max}} = 5.0, \delta = 10^{-5}$).
* ⚔️ **Byzantine Resilience under Non-IID Skew:** Robust aggregation primitives (Trimmed Mean, Coordinate Median, Krum) evaluated under severe non-IID statistical heterogeneity ($\operatorname{Dir}(\alpha=0.5)$ and $\operatorname{Dir}(\alpha=0.1)$) on vision workloads (ResNet-18 on CIFAR-10).
* 📜 **Statutory Compliance Engine & Attestation:** Automated evaluation of client identity, RBAC/ABAC access policies, and hardware root-of-trust attestation (TPM 2.0 / TEE Platform Configuration Register quotes) mapped directly to HIPAA \S164.312 and GDPR Art. 5/7/32.
* 🔄 **Dual-Action GDPR Article 17 Machine Unlearning:** Automated client credential eviction paired with gradient history un-rolling (`FedEraser` checkpoint purification) to eliminate revoked client data influence in under 120 ms.
* 🔗 **Tamper-Evident SHA-256 Audit Ledger:** Cryptographic hash-chained audit log linking all governance decisions, policy checks, and consent revocations for regulatory auditability.
* 📐 **Formal Game-Based Security Reduction:** Includes an appendix proof establishing threshold SecAgg privacy under the Decisional Diffie-Hellman (DDH) assumption.

---

## 🏗️ System Architecture

```
                    ┌─────────────────────────────────────────┐
                    │    FedGuard Governance Control Plane    │
                    │   - RBAC/ABAC Authorization Policy      │
                    │   - Hardware Attestation (TPM 2.0/TEE)  │
                    │   - SHA-256 Audit Ledger Persistence    │
                    └────────────────────┬────────────────────┘
                                         │ mTLS 1.3 / gRPC
         ┌───────────────────────────────┴───────────────────────────────┐
         │                                                               │
┌────────▼────────┐                                            ┌────────▼────────┐
│  Client Node 1  │                                            │  Client Node N  │
│  - ResNet-18    │◄───────────────── SecAgg ─────────────────►│  - ResNet-18    │
│  - RDP Noise    │        (X25519 ECDH + Shamir $k$-of-$N$)    │  - RDP Noise    │
└────────┬────────┘                                            └────────┬────────┘
         │                                                               │
         └───────────────────────────────┬───────────────────────────────┘
                                         │ Masked Updates
                            ┌────────────▼────────────┐
                            │   Central Aggregator    │
                            │  - Flower Orchestrator  │
                            │  - Robust Aggregation   │
                            └─────────────────────────┘
```

---

## 💻 Installation & Setup

### Prerequisites
* Python 3.12+
* PyTorch 2.2+
* LaTeX / MikTeX (optional, for compiling research paper PDF)

### Installation
Clone the repository and install `conclave` in editable development mode:

```bash
# 1. Clone repository
git clone https://github.com/Shariq12345/conclave_v1.git
cd conclave_v1

# 2. Create and activate virtual environment
python -m venv .venv
# On Windows:
.venv\Scripts\activate
# On Linux/macOS:
source .venv/bin/activate

# 3. Install package and dependencies
pip install -e .
```

---

## 🧪 Testing & Verification

Run the automated `pytest` verification suite covering governance policies, SecAgg primitives, Shamir reconstruction, RDP accounting, Byzantine aggregation, and audit ledgers:

```bash
pytest -v tests/
```

To run a specific test module (e.g., threshold SecAgg dropout recovery):
```bash
pytest -v tests/test_threshold_secagg.py
```

---

## ⚡ Interactive CLI & Benchmark Engine

### Running the Interactive CLI
Launch the interactive Conclave CLI:
```bash
conclave
```

### Running Real Deep Learning Workloads (ResNet-18 on CIFAR-10)
Run a training session with non-IID Dirichlet client partitioning ($\alpha = 0.5$):
```bash
python -m conclave.benchmarks.benchmark_engine --dataset cifar10 --model resnet18 --rounds 20 --clients 10
```

---

## 📊 Reproducing Research Paper Figures & Benchmarks

The repository includes a standalone automated script to generate all **10 publication-quality 300+ DPI vector PDF plots** featured in the research paper:

```bash
python benchmarks/generate_publication_figures.py
```

The generated figures are saved to `research_paper/figures/`:
1. `fig_secagg_overhead.pdf`: SecAgg execution latency vs. parameter dimension $d$.
2. `fig_privacy_budget.pdf`: RDP $(\epsilon, \delta)$ privacy budget composition over global rounds.
3. `fig_byzantine_accuracy.pdf`: Test accuracy under sign-flipping poisoning (FedAvg vs. Trimmed Mean vs. Krum).
4. `fig_audit_ledger_throughput.pdf`: SHA-256 audit ledger verification latency vs. event count.
5. `fig_gdpr_revocation.pdf`: Model accuracy trajectory during GDPR Art. 17 client unlearning.
6. `fig_component_ablation.pdf`: Micro-ablation breakdown of governance control plane latency.
7. `fig_baseline_runtime.pdf`: Runtime overhead comparison across FL baselines.
8. `fig_byzantine_sensitivity.pdf`: Sensitivity matrix of robust aggregators across adversary fractions ($f/N$).
9. `fig_resnet18_workload.pdf`: Workload latency scaling for ResNet-18 (11.17M parameters).
10. `fig_audit_ledger_verification.pdf`: Audit ledger tamper detection and verification throughput.

---

## 📖 Compiling the IEEE Transactions Research Paper

The complete LaTeX source code for the research paper is located in `research_paper/`. To compile the paper into PDF format:

```bash
cd research_paper
pdflatex -interaction=nonstopmode main.tex
pdflatex -interaction=nonstopmode main.tex
```

The output PDF will be generated as `research_paper/main.pdf` (15 pages, `IEEEtran.cls` format).

---

## 📁 Repository Structure

```
conclave_v1/
├── conclave/                       # Core FedGuard framework package
├── conclave/compliance/            # Regulatory engines (HIPAA, GDPR Art. 5/7/17/32)
├── conclave/crypto/                # Cryptographic primitives (X25519, RDP, Audit Ledger)
├── conclave/governance/            # Governance control plane, RBAC/ABAC policy engine
├── conclave/integrations/flower/   # Flower FL orchestrator integration & threshold SecAgg
├── conclave/models/                # PyTorch deep learning models (ResNet-18, CIFAR-10)
├── benchmarks/                     # Benchmark suite & vector plot generation script
├── tests/                          # Comprehensive pytest verification suite
├── research_paper/                 # Complete IEEE Transactions LaTeX manuscript source
│   ├── main.tex                    # Main LaTeX paper document
│   ├── sections/                   # Individual paper section TeX files (I - VII, Appendix A)
│   └── figures/                    # 10 publication-quality vector PDF plots
├── pyproject.toml                  # Python package configuration
└── README.md                       # Project documentation
```

---

## 📜 Citation & Reference

If you use **FedGuard** or **Conclave** in your research, please cite our paper:

```bibtex
@article{shaikh2026fedguard,
  title={FedGuard: A Governance Framework for Secure and Regulation-Compliant Federated Learning},
  author={Shaikh, Shariq and Nair, Maya},
  journal={},
  year={2026},
  note={Code available at: https://github.com/Shariq12345/conclave_v1}
}
```

---

## 📄 License

This project is licensed under the **MIT License** - see the [LICENSE](LICENSE) file for details.
