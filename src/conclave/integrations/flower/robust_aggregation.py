"""
conclave.integrations.flower.robust_aggregation
─────────────────────────────────────────────────
Byzantine-Resilient Aggregation Algorithms & Anomaly Detection.

Provides robust federated aggregation methods resistant to gradient poisoning
and backdoor attacks (Bonawitz / Blanchard et al. Krum, Trimmed Mean, Median),
combined with real-time update divergence anomaly detection.
"""

from __future__ import annotations

import math
from typing import List, Dict, Any, Tuple, Optional
import numpy as np


class TrimmedMeanAggregator:
    """Computes coordinate-wise trimmed mean across client update vectors.

    Trims the top and bottom beta fraction of values for each parameter index.
    beta = floor(N * trim_ratio).
    """

    def __init__(self, trim_ratio: float = 0.2):
        if not 0 <= trim_ratio < 0.5:
            raise ValueError("trim_ratio must be in [0, 0.5)")
        self.trim_ratio = trim_ratio

    def aggregate(self, client_updates: List[List[np.ndarray]]) -> List[np.ndarray]:
        if not client_updates:
            raise ValueError("client_updates list cannot be empty.")

        num_clients = len(client_updates)
        num_params = len(client_updates[0])
        beta = int(math.floor(num_clients * self.trim_ratio))

        aggregated = []
        for p_idx in range(num_params):
            # Stack tensors along client axis (shape: N, *param_shape)
            stacked = np.stack([client_updates[c_idx][p_idx] for c_idx in range(num_clients)], axis=0)

            if beta > 0 and num_clients - 2 * beta > 0:
                # Sort along client axis
                sorted_stacked = np.sort(stacked, axis=0)
                # Trim lowest beta and highest beta clients
                trimmed = sorted_stacked[beta : num_clients - beta]
                avg = np.mean(trimmed, axis=0)
            else:
                avg = np.mean(stacked, axis=0)

            aggregated.append(avg.astype(np.float32))

        return aggregated


class CoordinateMedianAggregator:
    """Computes coordinate-wise median vector across client updates."""

    def aggregate(self, client_updates: List[List[np.ndarray]]) -> List[np.ndarray]:
        if not client_updates:
            raise ValueError("client_updates list cannot be empty.")

        num_clients = len(client_updates)
        num_params = len(client_updates[0])

        aggregated = []
        for p_idx in range(num_params):
            stacked = np.stack([client_updates[c_idx][p_idx] for c_idx in range(num_clients)], axis=0)
            median_val = np.median(stacked, axis=0)
            aggregated.append(median_val.astype(np.float32))

        return aggregated


class KrumAggregator:
    """Blanchard et al. Krum / Multi-Krum Aggregator.

    For each client i, calculates the sum of L2 distances to its (N - f - 2)
    closest neighboring updates. Selects the update vector with minimum distance.
    """

    def __init__(self, f_byzantine: int = 1):
        self.f_byzantine = f_byzantine

    def aggregate(self, client_updates: List[List[np.ndarray]]) -> List[np.ndarray]:
        num_clients = len(client_updates)
        if num_clients < 2 * self.f_byzantine + 3:
            # Fallback to median if client count is too low for strict Krum bound
            return CoordinateMedianAggregator().aggregate(client_updates)

        # Flatten each client's parameters into a single 1D vector
        flattened_updates = []
        for client_weights in client_updates:
            flat = np.concatenate([w.ravel() for w in client_weights])
            flattened_updates.append(flat)

        num_neighbors = num_clients - self.f_byzantine - 2

        scores = []
        for i in range(num_clients):
            distances = []
            for j in range(num_clients):
                if i != j:
                    dist = np.linalg.norm(flattened_updates[i] - flattened_updates[j])
                    distances.append(dist)
            distances.sort()
            score = sum(distances[:num_neighbors])
            scores.append(score)

        best_client_idx = int(np.argmin(scores))
        return client_updates[best_client_idx]


class ByzantineAnomalyDetector:
    """Detects adversarial updates using Cosine Similarity and L2 Norm Divergence.

    Parameters
    ----------
    cosine_threshold : float
        Threshold below which cosine similarity indicates gradient sign-flipping.
    max_l2_ratio : float
        Maximum allowed ratio of a client's update norm relative to median norm.
    """

    def __init__(self, cosine_threshold: float = -0.1, max_l2_ratio: float = 3.0):
        self.cosine_threshold = cosine_threshold
        self.max_l2_ratio = max_l2_ratio

    @staticmethod
    def _flatten(weights: List[np.ndarray]) -> np.ndarray:
        return np.concatenate([w.ravel() for w in weights])

    def detect_anomalies(
        self,
        client_updates: Dict[str, List[np.ndarray]],
        global_weights: Optional[List[np.ndarray]] = None
    ) -> Dict[str, Dict[str, Any]]:
        """Evaluates client updates and returns anomaly flags per client.

        Returns
        -------
        Dict[str, Dict[str, Any]]
            Mapping client_id -> {'is_anomalous': bool, 'cosine_sim': float, 'l2_ratio': float, 'reason': str}
        """
        if not client_updates:
            return {}

        client_ids = list(client_updates.keys())
        flats = {cid: self._flatten(client_updates[cid]) for cid in client_ids}

        # Calculate coordinate-wise median as global consensus reference
        flat_matrix = np.stack(list(flats.values()), axis=0)
        consensus = np.median(flat_matrix, axis=0)
        consensus_norm = np.linalg.norm(consensus) + 1e-8

        results = {}
        for cid in client_ids:
            vec = flats[cid]
            vec_norm = np.linalg.norm(vec) + 1e-8

            # Cosine similarity relative to consensus median
            cosine_sim = float(np.dot(vec, consensus) / (vec_norm * consensus_norm))
            l2_ratio = float(vec_norm / consensus_norm)

            is_anomalous = False
            reasons = []

            if cosine_sim < self.cosine_threshold:
                is_anomalous = True
                reasons.append(f"Sign-Flipping Gradient Attack (Cosine Sim: {cosine_sim:.4f} < {self.cosine_threshold})")

            if l2_ratio > self.max_l2_ratio:
                is_anomalous = True
                reasons.append(f"Extreme L2 Norm Divergence (Ratio: {l2_ratio:.2f}x > {self.max_l2_ratio}x)")

            results[cid] = {
                "is_anomalous": is_anomalous,
                "cosine_sim": round(cosine_sim, 4),
                "l2_ratio": round(l2_ratio, 2),
                "reason": "; ".join(reasons) if is_anomalous else "Normal update"
            }

        return results
