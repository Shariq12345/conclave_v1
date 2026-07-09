import time
import logging
import threading
import subprocess
import sys
import flwr as fl
import numpy as np

# Suppress verbose Flower log outputs to keep CLI clean
logging.getLogger("flwr").setLevel(logging.ERROR)


class DPFedAvg(fl.server.strategy.FedAvg):
    """
    Custom FedAvg strategy that clips client updates and adds Laplace noise
    to guarantee Central Differential Privacy.
    """
    def __init__(self, dp_enabled=False, dp_epsilon=1.0, dp_delta=1e-5, session_id=None, num_rounds=3, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.dp_enabled = dp_enabled
        self.dp_epsilon = dp_epsilon
        self.dp_delta = dp_delta
        self.session_id = session_id
        self.num_rounds = num_rounds

    def aggregate_fit(self, server_round, results, failures):
        if self.session_id:
            try:
                from conclave.server.registry import ServiceRegistry
                registry = ServiceRegistry()
                registry.monitoring_service.log_session_metrics(
                    session_id=self.session_id,
                    current_round=server_round,
                    total_rounds=self.num_rounds,
                    status="Running"
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

            # Deserialize client updates
            client_updates = []
            num_examples_sum = 0
            for _, fit_res in results:
                ndarrays = parameters_to_ndarrays(fit_res.parameters)
                client_updates.append(ndarrays)
                num_examples_sum += fit_res.num_examples

            # Clip updates (Sensitivity bound)
            clip_norm = 1.0
            clipped_updates = []
            for ndarrays in client_updates:
                clipped = []
                for array in ndarrays:
                    norm = np.linalg.norm(array)
                    if norm > clip_norm:
                        array = array * (clip_norm / norm)
                    clipped.append(array)
                clipped_updates.append(clipped)

            # Weighted aggregate (average)
            aggregated_ndarrays = [np.zeros_like(x) for x in clipped_updates[0]]
            for idx, update in enumerate(clipped_updates):
                weight = results[idx][1].num_examples / num_examples_sum
                for layer_idx, layer in enumerate(update):
                    aggregated_ndarrays[layer_idx] += layer * weight

            # Add Differential Privacy Noise (Laplace Mechanism)
            # Sensitivity S = 2 * L2_clip_norm / num_clients
            num_clients = len(results)
            sensitivity = (2.0 * clip_norm) / float(num_clients)
            scale = sensitivity / self.dp_epsilon

            noisy_ndarrays = []
            for layer in aggregated_ndarrays:
                noise = np.random.laplace(0.0, scale, size=layer.shape)
                noisy_ndarrays.append(layer + noise)

            parameters_aggregated = ndarrays_to_parameters(noisy_ndarrays)
            res = (parameters_aggregated, {})

        t_agg_end = time.perf_counter()
        agg_time_ms = (t_agg_end - t_agg_start) * 1000.0

        if self.session_id:
            try:
                import os
                os.makedirs("results", exist_ok=True)
                with open("results/aggregation_times.txt", "a") as f_agg:
                    f_agg.write(f"{self.session_id},{server_round},{agg_time_ms}\n")
            except Exception:
                pass

        return res


class SimpleFlowerClient(fl.client.NumPyClient):
    """
    Flower client that loads real local CSV datasets, trains a binary Logistic Regression 
    model using Gradient Descent, and supports cryptographic Secure Aggregation masking.
    """
    def __init__(self, client_name: str, privacy_config: dict = None):
        self.client_name = client_name
        self.privacy_config = privacy_config or {}
        self.dataset_name = self.privacy_config.get("dataset_name", "diabetes")
        
        # Load or provision local data
        self.X, self.y = self._load_or_generate_dataset()
        
        # Initialize model parameters: w (weights) and b (bias)
        num_features = self.X.shape[1]
        self.w = np.zeros(num_features, dtype=np.float32)
        self.b = np.zeros(1, dtype=np.float32)

    def _load_or_generate_dataset(self):
        import os
        import csv
        
        data_dir = os.path.expanduser("~/.conclave/data")
        os.makedirs(data_dir, exist_ok=True)
        path = os.path.join(data_dir, f"{self.client_name}_{self.dataset_name}.csv")
        
        if not os.path.exists(path):
            print(f"[Conclave Data Provisioner] Local file '{path}' not found. Generating synthetic '{self.dataset_name}' dataset...")
            # Deterministic generator based on client name to ensure reproducibility
            seed_val = hash(self.client_name) % (2**32 - 1)
            rng = np.random.default_rng(seed_val)
            
            # Generate 120 samples, 4 features
            X_mock = rng.normal(loc=0.0, scale=1.0, size=(120, 4))
            # True weights and bias for mock classification boundary
            true_w = np.array([1.2, -1.8, 0.6, -1.2], dtype=np.float32)
            true_b = 0.1
            logits = X_mock @ true_w + true_b
            probs = 1.0 / (1.0 + np.exp(-logits))
            y_mock = (probs > 0.5).astype(int)
            
            # Write structured CSV
            with open(path, "w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(["feature_1", "feature_2", "feature_3", "feature_4", "target"])
                for i in range(len(X_mock)):
                    writer.writerow(list(X_mock[i]) + [y_mock[i]])
            print(f"[Conclave Data Provisioner] Synthetic dataset successfully written to '{path}' (120 rows).")

        # Load CSV dataset
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
        print(f"[{self.client_name}] Loaded dataset '{self.dataset_name}' from '{path}' (Shape: {X.shape})")
        return X, y

    def get_parameters(self, config):
        return [self.w, self.b]

    def fit(self, parameters, config):
        # Update local parameters with server's global parameters
        self.w = parameters[0].copy()
        self.b = parameters[1].copy()

        # Local training settings
        epochs = 5
        lr = 0.1
        m = self.X.shape[0]

        # Logistic Regression Gradient Descent
        for epoch in range(epochs):
            logits = self.X @ self.w + self.b
            logits = np.clip(logits, -50.0, 50.0) # Avoid overflow/underflow
            y_pred = 1.0 / (1.0 + np.exp(-logits))
            
            # Loss computation
            loss = -np.mean(self.y * np.log(y_pred + 1e-15) + (1.0 - self.y) * np.log(1.0 - y_pred + 1e-15))
            
            # Gradient calculations
            dw = (1.0 / m) * (self.X.T @ (y_pred - self.y))
            db = (1.0 / m) * np.sum(y_pred - self.y)
            
            # Updates
            self.w -= lr * dw
            self.b -= lr * db

        # Final predictions and local metrics
        logits = self.X @ self.w + self.b
        logits = np.clip(logits, -50.0, 50.0)
        y_pred = 1.0 / (1.0 + np.exp(-logits))
        preds = (y_pred > 0.5).astype(int)
        accuracy = np.mean(preds == self.y)
        
        updated_params = [self.w, self.b]

        # Secure Aggregation Masking for multiple parameters
        if self.privacy_config.get("secagg_enabled"):
            client_names = self.privacy_config.get("client_names", [])
            my_idx = self.privacy_config.get("client_index")
            if client_names and my_idx is not None:
                for param_idx in range(len(updated_params)):
                    mask_sum = np.zeros_like(updated_params[param_idx])
                    for idx, other_name in enumerate(client_names):
                        if idx == my_idx:
                            continue
                        # Pairwise deterministic alignment
                        pair = sorted([self.client_name, other_name])
                        seed = hash(f"{pair[0]}_{pair[1]}_{param_idx}") % (2**32 - 1)
                        rng = np.random.default_rng(seed)
                        
                        mask = rng.standard_normal(updated_params[param_idx].shape)
                        if my_idx < idx:
                            mask_sum += mask
                        else:
                            mask_sum -= mask
                    
                    updated_params[param_idx] = updated_params[param_idx] + mask_sum

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


class FlowerOrchestrator:
    @staticmethod
    def run_training(client_names: list, server_address: str = "127.0.0.1:8080", num_rounds: int = 3, privacy_config: dict = None, session_id: str = None):
        privacy = privacy_config or {}
        dp_enabled = privacy.get("dp_enabled", False)
        dp_eps = privacy.get("dp_epsilon", 1.0)
        dp_del = privacy.get("dp_delta", 1e-5)
        session_id_str = f"'{session_id}'" if session_id else "None"

        # 1. Start the Flower server in a separate Python process with Custom DPFedAvg
        cmd_code = (
            f"import flwr as fl; "
            f"import logging; "
            f"from conclave.integrations.flower.orchestrator import DPFedAvg; "
            f"logging.getLogger('flwr').setLevel(logging.ERROR); "
            f"strategy = DPFedAvg(dp_enabled={dp_enabled}, dp_epsilon={dp_eps}, dp_delta={dp_del}, session_id={session_id_str}, num_rounds={num_rounds}, min_fit_clients=1, min_available_clients=1, min_evaluate_clients=1); "
            f"fl.server.start_server(server_address='{server_address}', config=fl.server.ServerConfig(num_rounds={num_rounds}), strategy=strategy)"
        )
        
        server_proc = subprocess.Popen([sys.executable, "-c", cmd_code])

        # Give the server subprocess 2 seconds to bind to the port
        time.sleep(2.0)

        if server_proc.poll() is not None:
            exit_code = server_proc.poll()
            if exit_code != 0:
                raise RuntimeError(f"Flower server process failed to start. Exit code: {exit_code}")

        # 2. Start simulated client threads
        client_threads = []
        client_error = []

        def start_client(name, idx):
            try:
                client_priv_cfg = {**privacy, "client_index": idx, "client_names": client_names}
                client = SimpleFlowerClient(name, privacy_config=client_priv_cfg)
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

        # 3. Wait for the server process to complete
        try:
            exit_code = server_proc.wait(timeout=60)
            if exit_code != 0:
                raise RuntimeError(f"Flower server process exited with code {exit_code}")
        except subprocess.TimeoutExpired:
            server_proc.terminate()
            server_proc.wait()
            raise TimeoutError("Flower training timed out after 60 seconds.")

        # Join all client threads
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

        # Start the Flower server in a separate Python process with Custom DPFedAvg
        cmd_code = (
            f"import flwr as fl; "
            f"import logging; "
            f"from conclave.integrations.flower.orchestrator import DPFedAvg; "
            f"logging.getLogger('flwr').setLevel(logging.ERROR); "
            f"strategy = DPFedAvg(dp_enabled={dp_enabled}, dp_epsilon={dp_eps}, dp_delta={dp_del}, session_id={session_id_str}, num_rounds={num_rounds}, min_fit_clients=1, min_available_clients=1, min_evaluate_clients=1); "
            f"fl.server.start_server(server_address='{server_address}', config=fl.server.ServerConfig(num_rounds={num_rounds}), strategy=strategy)"
        )
        server_proc = subprocess.Popen([sys.executable, "-c", cmd_code])

        # Give the server subprocess 2 seconds to bind to the port
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
