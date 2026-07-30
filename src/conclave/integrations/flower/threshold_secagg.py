"""Threshold recovery primitives for dropout-resilient Secure Aggregation.

Clients use X25519 pairwise masks. Before a round, each client distributes
Shamir shares of its ephemeral private key to its peers. If that client drops
out, a threshold of surviving peers can reconstruct only the dropped client's
key so the server can cancel its unmatched masks. Active clients' keys remain
unrecoverable unless their own threshold of shares is released.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass

import numpy as np
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import x25519
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import hashes


# Larger than an X25519 private-key integer while retaining straightforward
# arithmetic for Shamir interpolation.
_PRIME = (1 << 521) - 1


class ShamirSecretSharing:
    """Minimal Shamir secret sharing over a large prime field."""

    @staticmethod
    def split(secret: bytes, threshold: int, share_count: int) -> list[tuple[int, int]]:
        if not 1 < threshold <= share_count:
            raise ValueError("threshold must be between 2 and share_count.")
        secret_int = int.from_bytes(secret, byteorder="big")
        if secret_int >= _PRIME:
            raise ValueError("secret is too large for the sharing field.")
        coefficients = [secret_int] + [secrets.randbelow(_PRIME) for _ in range(threshold - 1)]
        return [
            (x, sum(coefficient * pow(x, power, _PRIME) for power, coefficient in enumerate(coefficients)) % _PRIME)
            for x in range(1, share_count + 1)
        ]

    @staticmethod
    def recover(shares: list[tuple[int, int]], secret_length: int) -> bytes:
        if len(shares) < 2:
            raise ValueError("at least two shares are required for recovery.")
        if len({x for x, _ in shares}) != len(shares):
            raise ValueError("shares must have unique x coordinates.")
        secret = 0
        for i, (x_i, y_i) in enumerate(shares):
            numerator, denominator = 1, 1
            for j, (x_j, _) in enumerate(shares):
                if i != j:
                    numerator = (numerator * (-x_j)) % _PRIME
                    denominator = (denominator * (x_i - x_j)) % _PRIME
            secret = (secret + y_i * numerator * pow(denominator, -1, _PRIME)) % _PRIME
        return secret.to_bytes(secret_length, byteorder="big")


@dataclass
class ThresholdSecAggContext:
    """Round-scoped key material and recovery shares for threshold SecAgg."""

    participants: list[str]
    threshold: int
    keypairs: dict
    recovery_shares: dict[str, dict[str, tuple[int, int]]]

    @classmethod
    def create(cls, participants: list[str], threshold: int | None = None) -> "ThresholdSecAggContext":
        names = list(participants)
        if len(names) < 3:
            raise ValueError("Threshold SecAgg requires at least three participants.")
        if len(set(names)) != len(names):
            raise ValueError("Threshold SecAgg participant names must be unique.")
        threshold = threshold or min(len(names) - 1, max(2, len(names) // 2 + 1))
        if not 2 <= threshold <= len(names) - 1:
            raise ValueError("threshold must be between 2 and the number of peers per participant.")

        keypairs = {}
        for name in names:
            private_key = x25519.X25519PrivateKey.generate()
            keypairs[name] = (private_key, private_key.public_key())

        recovery_shares = {holder: {} for holder in names}
        for owner in names:
            private_bytes = keypairs[owner][0].private_bytes(
                serialization.Encoding.Raw,
                serialization.PrivateFormat.Raw,
                serialization.NoEncryption(),
            )
            holders = [name for name in names if name != owner]
            for holder, share in zip(holders, ShamirSecretSharing.split(private_bytes, threshold, len(holders))):
                recovery_shares[holder][owner] = share
        return cls(names, threshold, keypairs, recovery_shares)

    def shares_for_client(self, client_name: str) -> dict[str, tuple[int, int]]:
        """Return the recovery shares this client holds for other participants."""
        return dict(self.recovery_shares[client_name])

    def reconstruct_dropped_private_key(self, dropped_client: str, responding_clients: list[str]):
        shares = [self.recovery_shares[holder][dropped_client] for holder in responding_clients if dropped_client in self.recovery_shares[holder]]
        if len(shares) < self.threshold:
            raise ValueError(f"Insufficient recovery shares for dropped client '{dropped_client}'.")
        private_bytes = ShamirSecretSharing.recover(shares[:self.threshold], 32)
        return x25519.X25519PrivateKey.from_private_bytes(private_bytes)

    @staticmethod
    def _pairwise_mask(my_private, other_public, shape, parameter_index: int, positive: bool) -> np.ndarray:
        shared_secret = my_private.exchange(other_public)
        derived_key = HKDF(
            algorithm=hashes.SHA256(), length=32,
            salt=f"secagg_param_{parameter_index}".encode(),
            info=b"conclave_secagg_pairwise_key",
        ).derive(shared_secret)
        rng = np.random.default_rng(int.from_bytes(derived_key[:8], byteorder="big") % (2**32 - 1))
        mask = rng.standard_normal(shape, dtype=np.float32)
        return mask if positive else -mask

    def remove_dropped_client_masks(self, masked_parameter_sum: list[np.ndarray], active_clients: list[str], dropped_clients: list[str], responding_clients: list[str]) -> list[np.ndarray]:
        """Cancel unmatched masks from a sum of updates sent by active clients.

        The caller must collect recovery shares only after a client has been
        declared dropped. This operates on sums, not averaged parameters.
        """
        active = set(active_clients)
        if active & set(dropped_clients):
            raise ValueError("a client cannot be both active and dropped.")
        restored = [parameter.copy() for parameter in masked_parameter_sum]
        for dropped in dropped_clients:
            private_key = self.reconstruct_dropped_private_key(dropped, responding_clients)
            dropped_index = self.participants.index(dropped)
            for active_client in active_clients:
                active_index = self.participants.index(active_client)
                public_key = self.keypairs[active_client][1]
                for parameter_index, parameter in enumerate(restored):
                    # The active participant contributed the inverse of this
                    # dropped participant's mask, so add it back to cancel it.
                    parameter += self._pairwise_mask(
                        private_key, public_key, parameter.shape, parameter_index,
                        positive=dropped_index < active_index,
                    )
        return restored
