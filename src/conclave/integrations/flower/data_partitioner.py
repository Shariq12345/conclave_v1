"""
conclave.integrations.flower.data_partitioner
─────────────────────────────────────────────
Dirichlet Non-IID Data Partitioner for Federated Learning.
Partitions multi-class datasets across N client nodes using the Dirichlet distribution
Dir(alpha) to simulate heterogeneous client data distributions.
"""

import os
import numpy as np


class DirichletDataPartitioner:
    """
    Partitions dataset indices across N clients according to Dirichlet distribution Dir(alpha).
    - Alpha -> 0.1: Extreme Non-IID label skew (each client holds samples from 1-2 classes).
    - Alpha -> 1.0: Moderate Non-IID skew.
    - Alpha -> 10.0+: Approximately IID (homogeneous label distribution across clients).
    """
    def __init__(self, num_clients: int = 5, alpha: float = 0.5, seed: int = 42):
        self.num_clients = num_clients
        self.alpha = alpha
        self.seed = seed
        self.rng = np.random.default_rng(seed)

    def partition(self, X: np.ndarray, y: np.ndarray) -> dict:
        """
        Partitions feature matrix X and targets y across client nodes.
        Returns a dict mapping client_idx -> (X_client, y_client).
        """
        num_samples = len(y)
        classes = np.unique(y)
        num_classes = len(classes)

        client_indices = [[] for _ in range(self.num_clients)]

        for c in classes:
            # Get all sample indices for class c
            idx_k = np.where(y == c)[0]
            self.rng.shuffle(idx_k)

            # Sample Dirichlet proportions for class c across clients
            proportions = self.rng.dirichlet(np.repeat(self.alpha, self.num_clients))
            
            # Balance proportions based on existing client allocations
            proportions = np.array([p * (len(idx_j) < num_samples / self.num_clients) for p, idx_j in zip(proportions, client_indices)])
            if proportions.sum() == 0:
                proportions = np.ones(self.num_clients) / self.num_clients
            else:
                proportions = proportions / proportions.sum()

            # Split class indices across clients according to proportions
            split_points = (np.cumsum(proportions) * len(idx_k)).astype(int)[:-1]
            idx_batch = np.split(idx_k, split_points)

            for i in range(self.num_clients):
                client_indices[i].extend(idx_batch[i])

        client_data = {}
        for i in range(self.num_clients):
            indices = np.array(client_indices[i])
            if len(indices) == 0:
                # Fallback: assign random subset if client received 0 samples
                indices = self.rng.choice(num_samples, size=max(10, num_samples // (self.num_clients * 2)), replace=False)
            
            self.rng.shuffle(indices)
            client_data[i] = (X[indices], y[indices])

        return client_data

    def get_class_distribution_matrix(self, client_data: dict, num_classes: int) -> np.ndarray:
        """
        Computes an (N_clients x N_classes) matrix showing class counts per client.
        """
        matrix = np.zeros((self.num_clients, num_classes), dtype=int)
        for client_idx, (_, y_c) in client_data.items():
            for label in y_c:
                matrix[client_idx, int(label)] += 1
        return matrix
