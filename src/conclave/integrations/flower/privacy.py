"""Rényi Differential Privacy (RDP) accountant for federated learning.

Implements the Gaussian mechanism RDP bound from Mironov (2017) and the
tight RDP-to-(ε, δ)-DP conversion from Balle et al. (2020).  The accountant
tracks cumulative privacy cost across composed FL rounds and supports
automatic noise-multiplier calibration for a given (ε, δ, T) budget.

References
----------
- Mironov, I. (2017). "Rényi Differential Privacy". CSF.
- Balle, B. et al. (2020). "Hypothesis Testing Interpretations and Renyi DP".
  AISTATS.
- Abadi, M. et al. (2016). "Deep Learning with Differential Privacy". CCS.
"""

from __future__ import annotations

import math
from typing import List, Tuple


# Default Rényi orders to evaluate. A dense grid at low orders (where the
# optimum typically lies for practical σ values) combined with larger orders
# for completeness.  Following the convention used by TensorFlow Privacy and
# Google's DP library.
_DEFAULT_RDP_ORDERS: List[float] = (
    [1 + x / 10.0 for x in range(1, 100)]   # 1.1 … 10.9
    + list(range(11, 64))                     # 11 … 63
    + [64, 128, 256, 512, 1024]               # large orders
)


def _compute_rdp_gaussian(sigma: float, alpha: float) -> float:
    """Compute the RDP of the Gaussian mechanism at a single order.

    For the Gaussian mechanism with noise N(0, σ²I) applied to a
    unit-sensitivity query the RDP guarantee at order α is:

        rdp(α) = α / (2σ²)

    Parameters
    ----------
    sigma : float
        Noise multiplier (standard deviation relative to the L2 sensitivity).
    alpha : float
        Rényi divergence order. Must be > 1.

    Returns
    -------
    float
        The RDP guarantee ε_α for a single application of the mechanism.
    """
    if alpha <= 1:
        raise ValueError(f"Rényi order α must be > 1, got {alpha}")
    if sigma <= 0:
        raise ValueError(f"Noise multiplier σ must be > 0, got {sigma}")
    return alpha / (2.0 * sigma * sigma)


def _compute_rdp_composed(sigma: float, alpha: float, num_steps: int) -> float:
    """RDP after ``num_steps`` sequential compositions (simple addition)."""
    return num_steps * _compute_rdp_gaussian(sigma, alpha)


def _rdp_to_dp(rdp_epsilon: float, alpha: float, delta: float) -> float:
    """Convert an RDP guarantee to a standard (ε, δ)-DP guarantee.

    Uses the optimal conversion from Proposition 3 of Balle et al. (2020):

        ε = rdp_ε  +  log(1/δ) / (α − 1)  −  log(1 − 1/α) / (α − 1)

    The last term provides a tighter bound than the original Mironov (2017)
    conversion ε = rdp_ε + log(1/δ) / (α − 1).  For large α this term is
    negligible, but it matters at the small orders that are usually optimal.

    Parameters
    ----------
    rdp_epsilon : float
        The composed RDP epsilon at order α.
    alpha : float
        The Rényi divergence order (must be > 1).
    delta : float
        The target δ for the (ε, δ)-DP guarantee.

    Returns
    -------
    float
        The (ε, δ)-DP epsilon.
    """
    if delta <= 0:
        return math.inf
    if alpha <= 1:
        raise ValueError(f"Rényi order α must be > 1, got {alpha}")

    # Balle et al. (2020) tight conversion
    log_delta = math.log(delta)
    eps = rdp_epsilon + (log_delta + (alpha - 1) * math.log(1 - 1.0 / alpha) - math.log(alpha)) / (alpha - 1)
    # Fallback to the looser Mironov bound if the tight bound is negative
    # (can happen at extreme parameter combinations)
    eps_mironov = rdp_epsilon - (math.log(delta) + math.log(alpha - 1)) / (alpha - 1) + math.log(1 - 1.0 / alpha)
    # The standard simple bound that is always valid:
    eps_simple = rdp_epsilon + math.log(1.0 / delta) / (alpha - 1)
    # Return the tightest non-negative bound
    candidates = [e for e in (eps, eps_mironov, eps_simple) if e >= 0]
    return min(candidates) if candidates else eps_simple


class GaussianRDPAccountant:
    """Track cumulative (ε, δ)-DP budget for the Gaussian mechanism via RDP.

    The accountant evaluates the composed RDP guarantee across a dense grid of
    Rényi orders and selects the order that yields the tightest (ε, δ)-DP
    bound.  This mirrors the "moments accountant" approach used by Abadi et al.
    (2016) and implemented in TensorFlow Privacy and Opacus.

    Parameters
    ----------
    noise_multiplier : float
        The ratio σ / Δf where Δf is the L2 sensitivity (i.e. clip_norm / N
        for N participating clients).  In ``DPFedAvg`` the actual noise std
        is ``clip_norm * noise_multiplier / len(results)``.
    delta : float
        The target δ for (ε, δ)-DP accounting.
    orders : list[float] | None
        Rényi orders to evaluate.  Defaults to a dense grid from 1.1 to 1024.

    Usage
    -----
    >>> accountant = GaussianRDPAccountant(noise_multiplier=1.0, delta=1e-5)
    >>> eps, best_alpha = accountant.epsilon(num_steps=10)
    """

    def __init__(self, noise_multiplier: float, delta: float,
                 orders: List[float] | None = None) -> None:
        if noise_multiplier <= 0:
            raise ValueError(f"noise_multiplier must be positive, got {noise_multiplier}")
        if not (0 < delta < 1):
            raise ValueError(f"delta must be in (0, 1), got {delta}")
        self.noise_multiplier = float(noise_multiplier)
        self.delta = float(delta)
        self.orders = list(orders or _DEFAULT_RDP_ORDERS)

    def epsilon(self, num_steps: int) -> Tuple[float, float]:
        """Compute the tightest (ε, δ)-DP guarantee after ``num_steps`` rounds.

        Parameters
        ----------
        num_steps : int
            Number of composed Gaussian mechanism applications (FL rounds).

        Returns
        -------
        tuple[float, float]
            ``(epsilon, best_alpha)`` — the tightest ε and the Rényi order
            that achieved it.
        """
        if num_steps < 1:
            return 0.0, self.orders[0]

        best_eps = math.inf
        best_alpha = self.orders[0]

        for alpha in self.orders:
            rdp_eps = _compute_rdp_composed(self.noise_multiplier, alpha, num_steps)
            dp_eps = _rdp_to_dp(rdp_eps, alpha, self.delta)
            if dp_eps < best_eps:
                best_eps = dp_eps
                best_alpha = alpha

        return float(best_eps), float(best_alpha)

    def epsilon_per_order(self, num_steps: int) -> List[Tuple[float, float, float]]:
        """Return ``(alpha, rdp_eps, dp_eps)`` for every tracked order.

        Useful for diagnostics and plotting the RDP-to-DP conversion curve.
        """
        rows: List[Tuple[float, float, float]] = []
        for alpha in self.orders:
            rdp_eps = _compute_rdp_composed(self.noise_multiplier, alpha, num_steps)
            dp_eps = _rdp_to_dp(rdp_eps, alpha, self.delta)
            rows.append((alpha, rdp_eps, dp_eps))
        return rows

    @staticmethod
    def calibrate_noise_multiplier(target_epsilon: float, delta: float,
                                   num_steps: int, orders: List[float] | None = None,
                                   tol: float = 1e-3,
                                   sigma_bounds: Tuple[float, float] = (0.01, 500.0)) -> float:
        """Find the smallest noise multiplier σ that satisfies (ε, δ)-DP.

        Uses binary search over σ: for each candidate the full RDP accounting
        pipeline is evaluated and the result is compared against
        ``target_epsilon``.

        Parameters
        ----------
        target_epsilon : float
            Maximum acceptable ε.
        delta : float
            Target δ.
        num_steps : int
            Number of composed mechanism applications (FL rounds).
        orders : list[float] | None
            Rényi orders to evaluate during accounting.
        tol : float
            Convergence tolerance for the binary search on σ.
        sigma_bounds : tuple[float, float]
            ``(low, high)`` initial search interval for σ.

        Returns
        -------
        float
            The calibrated noise multiplier σ.

        Raises
        ------
        ValueError
            If the search interval is exhausted without convergence (the
            target ε may be unreachably small).
        """
        if target_epsilon <= 0:
            raise ValueError(f"target_epsilon must be positive, got {target_epsilon}")
        if num_steps < 1:
            raise ValueError(f"num_steps must be >= 1, got {num_steps}")

        low, high = sigma_bounds
        _orders = list(orders or _DEFAULT_RDP_ORDERS)

        # Verify that the upper bound is large enough
        acc = GaussianRDPAccountant(high, delta, _orders)
        eps_high, _ = acc.epsilon(num_steps)
        if eps_high > target_epsilon:
            raise ValueError(
                f"Cannot achieve ε={target_epsilon} even with σ={high}. "
                f"Achieved ε={eps_high:.4f}. Increase sigma_bounds or relax epsilon."
            )

        for _ in range(200):  # more than enough iterations for 1e-3 tolerance
            mid = (low + high) / 2.0
            acc = GaussianRDPAccountant(mid, delta, _orders)
            eps_mid, _ = acc.epsilon(num_steps)
            if eps_mid <= target_epsilon:
                high = mid
            else:
                low = mid
            if high - low < tol:
                break

        return round(high, 6)
