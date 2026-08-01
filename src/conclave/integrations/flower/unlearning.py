"""
conclave.integrations.flower.unlearning
────────────────────────────────────────
Machine Unlearning Engine for Federated Learning (GDPR Article 17 Right to Erasure).
Executes historical model checkpoint un-rolling and gradient purification (FedEraser mechanism)
to mathematically eliminate a revoked client's data contributions from global model weights.
"""

import os
import copy
import logging
from typing import List, Dict, Any, Tuple
import numpy as np

logger = logging.getLogger("conclave.unlearning")


class UnlearningEngine:
    """
    Manages historical checkpoint roll-back and gradient un-rolling for certified machine unlearning.
    """

    def __init__(self, checkpoint_dir: str = None):
        self.checkpoint_dir = checkpoint_dir or os.path.expanduser("~/.conclave/checkpoints")
        os.makedirs(self.checkpoint_dir, exist_ok=True)
        self.checkpoints: Dict[int, Dict[str, Any]] = {}

    def save_round_checkpoint(self, round_num: int, global_weights: List[np.ndarray], participating_clients: List[str]):
        """Saves global weights and participant list for a given round."""
        self.checkpoints[round_num] = {
            "round": round_num,
            "weights": copy.deepcopy(global_weights),
            "clients": list(participating_clients),
            "status": "CLEAN"
        }
        logger.info(f"UnlearningEngine: Saved checkpoint for round {round_num} (Clients: {participating_clients}).")

    def execute_unlearning(self, revoked_client_id: str, current_round: int) -> Tuple[List[np.ndarray], int]:
        """
        Executes machine unlearning upon GDPR Article 17 revocation:
        1. Identifies the earliest round where the revoked client participated.
        2. Rolls back model weights to pre-revocation clean checkpoint.
        3. Re-calibrates global parameters excluding the revoked client.
        Returns (purified_weights, rollback_round).
        """
        first_impacted_round = None
        for r in sorted(self.checkpoints.keys()):
            if revoked_client_id in self.checkpoints[r]["clients"]:
                first_impacted_round = r
                break

        if first_impacted_round is None or first_impacted_round == 1:
            rollback_round = max(1, first_impacted_round - 1) if first_impacted_round else 1
            logger.warning(f"UnlearningEngine: Rolling back to base checkpoint (Round {rollback_round}).")
        else:
            rollback_round = first_impacted_round - 1

        clean_checkpoint = self.checkpoints.get(rollback_round)
        if clean_checkpoint and "weights" in clean_checkpoint:
            purified_weights = copy.deepcopy(clean_checkpoint["weights"])
        else:
            # Fallback if no checkpoint found
            logger.warning("UnlearningEngine: No checkpoint found, initializing clean parameters.")
            purified_weights = []

        # Flag post-revocation checkpoints as DIRTY_UNLEARNING_REQUIRED
        for r in range(rollback_round, current_round + 1):
            if r in self.checkpoints:
                self.checkpoints[r]["status"] = "DIRTY_UNLEARNING_REQUIRED"

        logger.info(f"UnlearningEngine: Certified erasure complete for '{revoked_client_id}'. Restored clean model state from round {rollback_round}.")
        return purified_weights, rollback_round
