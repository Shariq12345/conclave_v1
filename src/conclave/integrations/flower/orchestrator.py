import time
import logging
import threading
import subprocess
import sys
import os
import flwr as fl
import numpy as np

# Suppress verbose Flower log outputs to keep CLI clean
logging.getLogger("flwr").setLevel(logging.ERROR)

# Check PyTorch availability
HAS_TORCH = False
try:
    import torch
    import torch.nn as nn
    import torch.optim as optim
    from torch.utils.data import DataLoader, TensorDataset
    HAS_TORCH = True
except ImportError:
    HAS_TORCH = False

# Check Cryptography availability
HAS_CRYPTO = False
try:
    from cryptography.hazmat.primitives.asymmetric import x25519
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF
    from cryptography.hazmat.primitives import hashes
    HAS_CRYPTO = True
except ImportError:
    HAS_CRYPTO = False

from conclave.integrations.flower.workloads import (
    build_cifar10_resnet18,
    is_real_workload,
    load_cifar10_partition,
)
from conclave.integrations.flower.threshold_secagg import ThresholdSecAggContext
from conclave.integrations.flower.privacy import GaussianRDPAccountant


class GovernanceMode:
    """
    Defines security & governance execution modes:
    - SECURE_AGGREGATION: Enforces X25519 + Shamir SecAgg + RDP Differential Privacy. Disables individual update inspection.
    - BYZANTINE_RESILIENT: Enforces Byzantine-robust aggregation (Trimmed Mean, Median, Krum) + RDP DP + L2 clipping. Disables SecAgg masking.
    - HYBRID_AUDITED: Evaluates and logs the active security mode per round in the audit ledger.
    """
    SECURE_AGGREGATION = "SECURE_AGGREGATION"
    BYZANTINE_RESILIENT = "BYZANTINE_RESILIENT"
    HYBRID_AUDITED = "HYBRID_AUDITED"


class CryptographicSecAgg:
    """
    Cryptographic Secure Aggregation Key Exchange & Masking.
    Uses Elliptic Curve Diffie-Hellman (X25519) + HKDF (SHA-256) to derive symmetric
    pairwise keys between client nodes. Generates zero-sum pseudo-random pairwise
    mask vectors to protect client weight updates.
    """
    @staticmethod
    def generate_keypair():
        if HAS_CRYPTO:
            priv_key = x25519.X25519PrivateKey.generate()
            pub_key = priv_key.public_key()
            return priv_key, pub_key
        return None, None

    @staticmethod
    def compute_pairwise_mask(my_priv_key, other_pub_key, param_shape, param_idx: int, is_lower_index: bool) -> np.ndarray:
        if HAS_CRYPTO and my_priv_key is not None and other_pub_key is not None:
            # ECDH shared secret
            shared_secret = my_priv_key.exchange(other_pub_key)
            # HKDF key derivation
            hkdf = HKDF(
                algorithm=hashes.SHA256(),
                length=32,
                salt=f"secagg_param_{param_idx}".encode(),
                info=b"conclave_secagg_pairwise_key",
            )
            derived_key = hkdf.derive(shared_secret)
            # Use derived key as seed for PRNG
            seed = int.from_bytes(derived_key[:8], byteorder="big") % (2**32 - 1)
        else:
            # Fallback hash-seeding for lightweight environments
            pair_str = f"secagg_{param_idx}_{id(my_priv_key)}_{id(other_pub_key)}"
            seed = hash(pair_str) % (2**32 - 1)

        rng = np.random.default_rng(seed)
        mask = rng.standard_normal(param_shape, dtype=np.float32)
        return mask if is_lower_index else -mask

    @staticmethod
    def apply_pairwise_masks(client_name: str, my_idx: int, client_names: list, parameters: list, keypairs: dict = None) -> list:
        if not client_names or my_idx is None:
            return parameters

        masked_params = [p.copy() for p in parameters]
        for param_idx in range(len(masked_params)):
            mask_sum = np.zeros_like(masked_params[param_idx], dtype=np.float32)
            for idx, other_name in enumerate(client_names):
                if idx == my_idx:
                    continue
                
                # Pairwise key agreement
                my_priv = keypairs.get(client_name, (None, None))[0] if keypairs else None
                other_pub = keypairs.get(other_name, (None, None))[1] if keypairs else None

                mask = CryptographicSecAgg.compute_pairwise_mask(
                    my_priv_key=my_priv,
                    other_pub_key=other_pub,
                    param_shape=masked_params[param_idx].shape,
                    param_idx=param_idx,
                    is_lower_index=(my_idx < idx)
                )
                mask_sum += mask

            masked_params[param_idx] = masked_params[param_idx] + mask_sum

        return masked_params


class DPFedAvg(fl.server.strategy.FedAvg):
    """FedAvg with calibrated central Gaussian DP and multi-order RDP accounting."""
    def __init__(self, dp_enabled=False, dp_epsilon=1.0, dp_delta=1e-5, clip_norm=1.0,
                 noise_multiplier=None, session_id=None, organization_ids=None, num_rounds=3, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.dp_enabled = dp_enabled
        self.dp_epsilon = float(dp_epsilon)
        self.dp_delta = float(dp_delta)
        self.clip_norm = float(clip_norm)
        self.session_id = session_id
        self.organization_ids = list(organization_ids or [])
        self.num_rounds = int(num_rounds)
        if dp_enabled:
            self.noise_multiplier = float(noise_multiplier) if noise_multiplier is not None else GaussianRDPAccountant.calibrate_noise_multiplier(
                self.dp_epsilon, self.dp_delta, self.num_rounds
            )
            self.accountant = GaussianRDPAccountant(self.noise_multiplier, self.dp_delta)
        else:
            self.noise_multiplier = 0.0
            self.accountant = None
        self.accumulated_rdp_eps = 0.0
        self.renyi_order = None

    def compute_rdp_epsilon(self, alpha=None, current_round=1):
        """Return the tightest composed epsilon; ``alpha`` is retained for API compatibility."""
        if not self.dp_enabled:
            return 0.0
        epsilon, _ = self.accountant.epsilon(current_round)
        return float(epsilon)

    def _record_privacy_budget(self, server_round: int):
        self.accumulated_rdp_eps, self.renyi_order = self.accountant.epsilon(server_round)
        if not self.session_id:
            return
        try:
            from conclave.server.registry import ServiceRegistry
            monitoring = ServiceRegistry().monitoring_service
            for organization_id in self.organization_ids:
                monitoring.log_privacy_budget(
                    organization_id=organization_id,
                    session_id=self.session_id,
                    current_round=server_round,
                    epsilon=self.accumulated_rdp_eps,
                    delta=self.dp_delta,
                    noise_multiplier=self.noise_multiplier,
                    clip_norm=self.clip_norm,
                    renyi_order=self.renyi_order,
                    budget_epsilon=self.dp_epsilon,
                )
        except Exception:
            # Training must not silently lose its DP guarantee, but an external
            # monitoring failure should not corrupt the FL aggregation result.
            logging.exception("Could not persist the differential-privacy budget metric")

    def aggregate_fit(self, server_round, results, failures):
        if self.session_id:
            try:
                from conclave.server.registry import ServiceRegistry
                ServiceRegistry().monitoring_service.log_session_metrics(
                    session_id=self.session_id, current_round=server_round,
                    total_rounds=self.num_rounds, status="Running"
                )
            except Exception:
                pass
        if not results:
            return None, {}

        t_agg_start = time.perf_counter()
        if not self.dp_enabled:
            res = super().aggregate_fit(server_round, results, failures)
        else:
            from flwr.common import parameters_to_ndarrays, ndarrays_to_parameters
            client_updates = []
            num_examples_sum = 0
            for _, fit_res in results:
                client_updates.append(parameters_to_ndarrays(fit_res.parameters))
                num_examples_sum += fit_res.num_examples

            clipped_updates = []
            for ndarrays in client_updates:
                total_norm = np.sqrt(sum(np.sum(np.square(arr)) for arr in ndarrays))
                scale = min(1.0, self.clip_norm / (total_norm + 1e-10))
                clipped_updates.append([arr * scale for arr in ndarrays])

            aggregated_ndarrays = [np.zeros_like(x, dtype=np.float32) for x in clipped_updates[0]]
            for idx, update in enumerate(clipped_updates):
                weight = results[idx][1].num_examples / float(num_examples_sum)
                for layer_idx, layer in enumerate(update):
                    aggregated_ndarrays[layer_idx] += layer * weight

            # The aggregate sensitivity is C / N for N equally participating clients.
            sigma = (self.clip_norm * self.noise_multiplier) / float(len(results))
            noisy_ndarrays = [
                layer + np.random.normal(0.0, sigma, size=layer.shape).astype(np.float32)
                for layer in aggregated_ndarrays
            ]
            self._record_privacy_budget(server_round)
            print(
                f"[Conclave RDP Accountant] Round {server_round}/{self.num_rounds}: "
                f"epsilon={self.accumulated_rdp_eps:.4f}, delta={self.dp_delta}, "
                f"order={self.renyi_order:g}, sigma={self.noise_multiplier:.4f}"
            )
            res = (ndarrays_to_parameters(noisy_ndarrays), {
                "accumulated_rdp_epsilon": self.accumulated_rdp_eps,
                "renyi_order": self.renyi_order,
                "noise_multiplier": self.noise_multiplier,
            })

        agg_time_ms = (time.perf_counter() - t_agg_start) * 1000.0
        if self.session_id:
            try:
                os.makedirs("results", exist_ok=True)
                with open("results/aggregation_times.txt", "a") as f_agg:
                    f_agg.write(f"{self.session_id},{server_round},{agg_time_ms}\n")
            except Exception:
                pass
        return res


if HAS_TORCH:
    class TabularMLP(nn.Module):
        """PyTorch Multi-Layer Perceptron (MLP) for Tabular Datasets."""
        def __init__(self, input_dim=4, hidden_dim=16, output_dim=2):
            super().__init__()
            self.net = nn.Sequential(
                nn.Linear(input_dim, hidden_dim),
                nn.BatchNorm1d(hidden_dim),
                nn.ReLU(),
                nn.Dropout(0.1),
                nn.Linear(hidden_dim, hidden_dim // 2),
                nn.ReLU(),
                nn.Linear(hidden_dim // 2, output_dim)
            )

        def forward(self, x):
            return self.net(x)

    class VisionCNN(nn.Module):
        """PyTorch Convolutional Neural Network (CNN) for Image Datasets (e.g. MNIST / MedMNIST)."""
        def __init__(self, in_channels=1, num_classes=10):
            super().__init__()
            self.features = nn.Sequential(
                nn.Conv2d(in_channels, 16, kernel_size=3, padding=1),
                nn.BatchNorm2d(16),
                nn.ReLU(),
                nn.MaxPool2d(2, 2),
                nn.Conv2d(16, 32, kernel_size=3, padding=1),
                nn.BatchNorm2d(32),
                nn.ReLU(),
                nn.MaxPool2d(2, 2)
            )
            self.classifier = nn.Sequential(
                nn.Flatten(),
                nn.Linear(32 * 7 * 7, 64),
                nn.ReLU(),
                nn.Linear(64, num_classes)
            )

        def forward(self, x):
            x = self.features(x)
            return self.classifier(x)


class PyTorchFlowerClient(fl.client.NumPyClient):
    """
    Enterprise PyTorch Flower Client supporting MLP & CNN deep learning models,
    DataLoader batching, and Cryptographic Secure Aggregation masking.
    """
    def __init__(self, client_name: str, privacy_config: dict = None):
        self.client_name = client_name
        self.privacy_config = privacy_config or {}
        self.dataset_name = self.privacy_config.get("dataset_name", "diabetes")
        self.model_type = self.privacy_config.get("model_type", "mlp")

        if not HAS_TORCH:
            raise RuntimeError("PyTorch is not installed. Fall back to SimpleFlowerClient.")
        self.device = torch.device(self.privacy_config.get("device", "cuda" if torch.cuda.is_available() else "cpu"))

        self.real_workload = is_real_workload(self.dataset_name)
        self.train_loader, self.test_loader, self.input_dim, self.num_classes = self._prepare_data()

        # CIFAR-10 sessions use a CIFAR-10-adapted ResNet-18. The MLP remains
        # available for lightweight tabular demonstrations.
        if self.real_workload:
            self.model = build_cifar10_resnet18(num_classes=self.num_classes)
        else:
            self.model = TabularMLP(input_dim=self.input_dim, hidden_dim=16, output_dim=self.num_classes)
        self.model.to(self.device)

        self.criterion = nn.CrossEntropyLoss()
        self.optimizer = optim.Adam(self.model.parameters(), lr=0.01)

    def _prepare_data(self):
        if is_real_workload(self.dataset_name):
            client_index = int(self.privacy_config.get("client_index", 0))
            num_clients = max(1, len(self.privacy_config.get("client_names", [])))
            train_loader, test_loader = load_cifar10_partition(
                client_index=client_index,
                num_clients=num_clients,
                data_dir=self.privacy_config.get("data_dir"),
                dirichlet_alpha=float(self.privacy_config.get("dirichlet_alpha", 0.5)),
                seed=int(self.privacy_config.get("partition_seed", 42)),
                batch_size=int(self.privacy_config.get("batch_size", 32)),
                num_workers=int(self.privacy_config.get("num_workers", 0)),
                download=bool(self.privacy_config.get("download_dataset", True)),
            )
            return train_loader, test_loader, 3, 10

        # Generate or load dataset
        fallback_client = SimpleFlowerClient(self.client_name, self.privacy_config)
        X, y = fallback_client.X, fallback_client.y

        # Convert to PyTorch Tensors
        X_tensor = torch.tensor(X, dtype=torch.float32)
        y_tensor = torch.tensor(y, dtype=torch.long)

        dataset = TensorDataset(X_tensor, y_tensor)
        train_size = int(0.8 * len(dataset))
        test_size = len(dataset) - train_size
        train_ds, test_ds = torch.utils.data.random_split(dataset, [train_size, test_size])

        train_loader = DataLoader(train_ds, batch_size=16, shuffle=True)
        test_loader = DataLoader(test_ds, batch_size=16, shuffle=False)

        num_classes = len(np.unique(y)) if len(np.unique(y)) > 1 else 2
        return train_loader, test_loader, X.shape[1], num_classes

    def get_parameters(self, config):
        # Aggregate trainable parameters only. BatchNorm buffers stay local,
        # avoiding invalid averaging of integer tracking counters.
        return [param.detach().cpu().numpy() for param in self.model.parameters()]

    def _set_parameters(self, parameters):
        for parameter, value in zip(self.model.parameters(), parameters):
            parameter.data.copy_(torch.from_numpy(value).to(self.device, dtype=parameter.dtype))

    def fit(self, parameters, config):
        self._set_parameters(parameters)

        self.model.train()
        epochs = int(self.privacy_config.get("local_epochs", 1 if self.real_workload else 3))
        for epoch in range(epochs):
            for batch_X, batch_y in self.train_loader:
                batch_X, batch_y = batch_X.to(self.device), batch_y.to(self.device)
                self.optimizer.zero_grad()
                outputs = self.model(batch_X)
                loss = self.criterion(outputs, batch_y)
                loss.backward()
                self.optimizer.step()

        updated_params = self.get_parameters(config)

        # Apply Cryptographic Secure Aggregation
        if self.privacy_config.get("secagg_enabled"):
            client_names = self.privacy_config.get("client_names", [])
            my_idx = self.privacy_config.get("client_index")
            keypairs = self.privacy_config.get("secagg_keypairs", {})
            updated_params = CryptographicSecAgg.apply_pairwise_masks(
                client_name=self.client_name,
                my_idx=my_idx,
                client_names=client_names,
                parameters=updated_params,
                keypairs=keypairs
            )

        loss_val, acc_val = self._evaluate_local()
        return updated_params, len(self.train_loader.dataset), {"accuracy": acc_val, "loss": loss_val}

    def evaluate(self, parameters, config):
        self._set_parameters(parameters)

        loss_val, acc_val = self._evaluate_local()
        return loss_val, len(self.test_loader.dataset), {"accuracy": acc_val}

    def _evaluate_local(self):
        self.model.eval()
        total_loss = 0.0
        correct = 0
        total = 0
        with torch.no_grad():
            for batch_X, batch_y in self.test_loader:
                batch_X, batch_y = batch_X.to(self.device), batch_y.to(self.device)
                outputs = self.model(batch_X)
                loss = self.criterion(outputs, batch_y)
                total_loss += loss.item() * len(batch_y)
                _, preds = torch.max(outputs, 1)
                correct += (preds == batch_y).sum().item()
                total += len(batch_y)
        avg_loss = total_loss / max(1, total)
        acc = correct / max(1, total)
        return float(avg_loss), float(acc)


class SimpleFlowerClient(fl.client.NumPyClient):
    """
    Lightweight Flower client that loads local CSV datasets and trains Logistic Regression.
    Supports Cryptographic Secure Aggregation masking.
    """
    def __init__(self, client_name: str, privacy_config: dict = None):
        self.client_name = client_name
        self.privacy_config = privacy_config or {}
        self.dataset_name = self.privacy_config.get("dataset_name", "diabetes")

        self.X, self.y = self._load_or_generate_dataset()

        num_features = self.X.shape[1]
        self.w = np.zeros(num_features, dtype=np.float32)
        self.b = np.zeros(1, dtype=np.float32)

    def _load_or_generate_dataset(self):
        import csv
        data_dir = os.path.expanduser("~/.conclave/data")
        os.makedirs(data_dir, exist_ok=True)
        path = os.path.join(data_dir, f"{self.client_name}_{self.dataset_name}.csv")

        if not os.path.exists(path):
            seed_val = hash(self.client_name) % (2**32 - 1)
            rng = np.random.default_rng(seed_val)
            X_mock = rng.normal(loc=0.0, scale=1.0, size=(120, 4))
            true_w = np.array([1.2, -1.8, 0.6, -1.2], dtype=np.float32)
            true_b = 0.1
            logits = X_mock @ true_w + true_b
            probs = 1.0 / (1.0 + np.exp(-logits))
            y_mock = (probs > 0.5).astype(int)

            with open(path, "w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(["feature_1", "feature_2", "feature_3", "feature_4", "target"])
                for i in range(len(X_mock)):
                    writer.writerow(list(X_mock[i]) + [y_mock[i]])

        X_list = []
        y_list = []
        with open(path, "r") as f:
            reader = csv.reader(f)
            header = next(reader)
            target_idx = -1
            for idx, col in enumerate(header):
                if col.lower() in ("target", "label", "y", "status"):
                    target_idx = idx
                    break

            for row in reader:
                if not row:
                    continue
                try:
                    row_float = [float(val) for val in row]
                except ValueError:
                    continue

                if target_idx != -1:
                    y_val = row_float[target_idx]
                    X_vals = [row_float[i] for i in range(len(row_float)) if i != target_idx]
                else:
                    y_val = row_float[-1]
                    X_vals = row_float[:-1]

                X_list.append(X_vals)
                y_list.append(y_val)

        X = np.array(X_list, dtype=np.float32)
        y = np.array(y_list, dtype=np.float32)
        return X, y

    def get_parameters(self, config):
        return [self.w, self.b]

    def fit(self, parameters, config):
        self.w = parameters[0].copy()
        self.b = parameters[1].copy()

        epochs = 5
        lr = 0.1
        m = self.X.shape[0]

        for epoch in range(epochs):
            logits = self.X @ self.w + self.b
            logits = np.clip(logits, -50.0, 50.0)
            y_pred = 1.0 / (1.0 + np.exp(-logits))

            loss = -np.mean(self.y * np.log(y_pred + 1e-15) + (1.0 - self.y) * np.log(1.0 - y_pred + 1e-15))
            dw = (1.0 / m) * (self.X.T @ (y_pred - self.y))
            db = (1.0 / m) * np.sum(y_pred - self.y)

            self.w -= lr * dw
            self.b -= lr * db

        logits = self.X @ self.w + self.b
        logits = np.clip(logits, -50.0, 50.0)
        y_pred = 1.0 / (1.0 + np.exp(-logits))
        preds = (y_pred > 0.5).astype(int)
        accuracy = np.mean(preds == self.y)

        updated_params = [self.w, self.b]

        if self.privacy_config.get("secagg_enabled"):
            client_names = self.privacy_config.get("client_names", [])
            my_idx = self.privacy_config.get("client_index")
            keypairs = self.privacy_config.get("secagg_keypairs", {})
            updated_params = CryptographicSecAgg.apply_pairwise_masks(
                client_name=self.client_name,
                my_idx=my_idx,
                client_names=client_names,
                parameters=updated_params,
                keypairs=keypairs
            )

        return updated_params, len(self.y), {"accuracy": float(accuracy), "loss": float(loss)}

    def evaluate(self, parameters, config):
        w = parameters[0]
        b = parameters[1]

        logits = self.X @ w + b
        logits = np.clip(logits, -50.0, 50.0)
        y_pred = 1.0 / (1.0 + np.exp(-logits))

        loss = -np.mean(self.y * np.log(y_pred + 1e-15) + (1.0 - self.y) * np.log(1.0 - y_pred + 1e-15))
        preds = (y_pred > 0.5).astype(int)
        accuracy = np.mean(preds == self.y)

        return float(loss), len(self.y), {"accuracy": float(accuracy)}


def create_flower_client(client_name: str, privacy_config: dict = None):
    """Select the PyTorch trainer when available, with a safe legacy fallback."""
    privacy = privacy_config or {}
    use_pytorch = privacy.get("use_pytorch", HAS_TORCH)
    if use_pytorch and HAS_TORCH:
        return PyTorchFlowerClient(client_name, privacy_config=privacy)
    return SimpleFlowerClient(client_name, privacy_config=privacy)


class FlowerOrchestrator:
    @staticmethod
    def run_training(client_names: list, server_address: str = "127.0.0.1:8080", num_rounds: int = 3, privacy_config: dict = None, session_id: str = None):
        privacy = privacy_config or {}
        dp_enabled = privacy.get("dp_enabled", False)
        dp_eps = privacy.get("dp_epsilon", 1.0)
        dp_del = privacy.get("dp_delta", 1e-5)
        session_id_str = f"'{session_id}'" if session_id else "None"

        # Pre-generate ECDH keypairs for cryptographic SecAgg if active
        secagg_keypairs = {}
        secagg_context = None
        if privacy.get("secagg_enabled"):
            # Each round setup creates ephemeral X25519 keys and distributes
            # Shamir recovery shares to peers. The client path remains
            # compatible with the existing pairwise-mask interface.
            configured_threshold = privacy.get("secagg_threshold")
            secagg_context = ThresholdSecAggContext.create(
                client_names, threshold=int(configured_threshold) if configured_threshold is not None else None
            )
            secagg_keypairs = secagg_context.keypairs

        # 1. Start the Flower server process
        cmd_code = (
            f"import flwr as fl; "
            f"import logging; "
            f"from conclave.integrations.flower.orchestrator import DPFedAvg; "
            f"logging.getLogger('flwr').setLevel(logging.ERROR); "
            f"strategy = DPFedAvg(dp_enabled={dp_enabled}, dp_epsilon={dp_eps}, dp_delta={dp_del}, session_id={session_id_str}, num_rounds={num_rounds}, min_fit_clients=1, min_available_clients=1, min_evaluate_clients=1); "
            f"fl.server.start_server(server_address='{server_address}', config=fl.server.ServerConfig(num_rounds={num_rounds}), strategy=strategy)"
        )

        server_proc = subprocess.Popen([sys.executable, "-c", cmd_code])
        time.sleep(2.0)

        if server_proc.poll() is not None:
            exit_code = server_proc.poll()
            if exit_code != 0:
                raise RuntimeError(f"Flower server process failed to start. Exit code: {exit_code}")

        # 2. Start client threads
        client_threads = []
        client_error = []

        def start_client(name, idx):
            try:
                client_priv_cfg = {
                    **privacy,
                    "client_index": idx,
                    "client_names": client_names,
                    "secagg_keypairs": secagg_keypairs,
                    "secagg_recovery_shares": secagg_context.shares_for_client(name) if secagg_context else {},
                    "secagg_threshold": secagg_context.threshold if secagg_context else None,
                }

                client = create_flower_client(name, privacy_config=client_priv_cfg)

                fl.client.start_numpy_client(
                    server_address=server_address,
                    client=client
                )
            except Exception as e:
                client_error.append((name, e))

        for idx, name in enumerate(client_names):
            t = threading.Thread(target=start_client, args=(name, idx))
            t.daemon = True
            t.start()
            client_threads.append(t)
            time.sleep(0.1)

        # 3. Wait for completion
        try:
            exit_code = server_proc.wait(timeout=60)
            if exit_code != 0:
                raise RuntimeError(f"Flower server process exited with code {exit_code}")
        except subprocess.TimeoutExpired:
            server_proc.terminate()
            server_proc.wait()
            raise TimeoutError("Flower training timed out after 60 seconds.")

        for t in client_threads:
            t.join(timeout=5)

        if client_error:
            client_errs = ", ".join(f"{name}: {str(err)}" for name, err in client_error)
            raise RuntimeError(f"Flower client errors occurred: {client_errs}")

    @classmethod
    def run_server_only(cls, server_address: str = "127.0.0.1:8080", num_rounds: int = 3, timeout_secs: int = 60, privacy_config: dict = None, session_id: str = None):
        privacy = privacy_config or {}
        dp_enabled = privacy.get("dp_enabled", False)
        dp_eps = privacy.get("dp_epsilon", 1.0)
        dp_del = privacy.get("dp_delta", 1e-5)
        session_id_str = f"'{session_id}'" if session_id else "None"

        cmd_code = (
            f"import flwr as fl; "
            f"import logging; "
            f"from conclave.integrations.flower.orchestrator import DPFedAvg; "
            f"logging.getLogger('flwr').setLevel(logging.ERROR); "
            f"strategy = DPFedAvg(dp_enabled={dp_enabled}, dp_epsilon={dp_eps}, dp_delta={dp_del}, session_id={session_id_str}, num_rounds={num_rounds}, min_fit_clients=1, min_available_clients=1, min_evaluate_clients=1); "
            f"fl.server.start_server(server_address='{server_address}', config=fl.server.ServerConfig(num_rounds={num_rounds}), strategy=strategy)"
        )
        server_proc = subprocess.Popen([sys.executable, "-c", cmd_code])
        time.sleep(2.0)

        if server_proc.poll() is not None:
            exit_code = server_proc.poll()
            if exit_code != 0:
                raise RuntimeError(f"Flower server process failed to start. Exit code: {exit_code}")

        try:
            exit_code = server_proc.wait(timeout=timeout_secs)
            if exit_code != 0:
                raise RuntimeError(f"Flower server process exited with code {exit_code}")
        except subprocess.TimeoutExpired:
            server_proc.terminate()
            server_proc.wait()
            raise TimeoutError(f"Flower training timed out after {timeout_secs} seconds.")
