from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FillModel:
    """
    Models execution slippage and fees for backtesting.

    Supported slippage models:
    - fixed_cents: Fixed dollar amount slippage per share (e.g., 0.02 = 2 cents)
    - pct_of_price: Percentage of price slippage (e.g., 0.001 = 0.1%)
    - tiered: Tiered slippage based on price level

    For all models, slippage is applied adversely:
    - Entry: price + slippage (worse fill for longs)
    - Exit: price - slippage (worse fill for longs)

    FEE CONVENTION:
    - fees_per_trade: Fee applied ONCE per round-trip (on exit only).
      This represents the total cost of opening and closing a position.
      Example: fees_per_trade=1.0 means $1 total fee per round-trip.

    The fee is deducted from cash and P&L on exit:
      pnl = (exit_px - entry_px) * qty - fees_per_trade
      cash += (exit_px * qty - fees_per_trade)

    This is mathematically equivalent to splitting the fee half on entry
    and half on exit, or using per-order fees of fees_per_trade/2.
    """

    model: str
    cents: float = 0.0  # Used by fixed_cents model
    pct: float = 0.0  # Used by pct_of_price model

    # Fee applied once per round-trip (on exit). See docstring for convention.
    fees_per_trade: float = 0.0

    # Tiered slippage thresholds (for tiered model)
    tier_thresholds: tuple[float, ...] = (5.0, 10.0, 20.0)  # Price thresholds
    tier_cents: tuple[float, ...] = (0.02, 0.03, 0.05, 0.10)  # Slippage for each tier

    def apply_entry(self, price: float) -> float:
        """Apply slippage to entry price (worse fill = higher price for longs)."""
        return price + self._compute_slippage(price)

    def apply_exit(self, price: float) -> float:
        """Apply slippage to exit price (worse fill = lower price for longs)."""
        return price - self._compute_slippage(price)

    def _compute_slippage(self, price: float) -> float:
        """Compute slippage amount based on the model type."""
        if self.model == "fixed_cents":
            return self.cents

        if self.model == "pct_of_price":
            return price * self.pct

        if self.model == "tiered":
            # Find the appropriate tier based on price
            for i, threshold in enumerate(self.tier_thresholds):
                if price < threshold:
                    return self.tier_cents[i]
            # Price is above all thresholds, use the last (highest) tier
            return self.tier_cents[-1]

        raise ValueError(f"Unknown slippage model: {self.model}")

    def describe(self) -> str:
        """Return a human-readable description of the slippage model."""
        if self.model == "fixed_cents":
            return f"Fixed ${self.cents:.4f}/share"
        if self.model == "pct_of_price":
            return f"{self.pct * 100:.3f}% of price"
        if self.model == "tiered":
            tiers = ", ".join(
                f"<${t}: ${c:.2f}" for t, c in zip(self.tier_thresholds, self.tier_cents[:-1])
            )
            return f"Tiered: {tiers}, >=${self.tier_thresholds[-1]}: ${self.tier_cents[-1]:.2f}"
        return f"Unknown model: {self.model}"


def create_fill_model(
    model: str = "fixed_cents",
    cents: float = 0.02,
    pct: float = 0.001,
    fees_per_trade: float = 0.0,
    tier_thresholds: tuple[float, ...] | None = None,
    tier_cents: tuple[float, ...] | None = None,
) -> FillModel:
    """
    Factory function to create FillModel instances.

    Args:
        model: Slippage model type ("fixed_cents", "pct_of_price", or "tiered")
        cents: Fixed cents slippage (for fixed_cents model)
        pct: Percentage slippage (for pct_of_price model, e.g., 0.001 = 0.1%)
        fees_per_trade: Fee per round-trip (applied once on exit, see FillModel docs)
        tier_thresholds: Price thresholds for tiered model
        tier_cents: Slippage amounts for each tier

    Returns:
        Configured FillModel instance
    """
    if tier_thresholds is None:
        tier_thresholds = (5.0, 10.0, 20.0)
    if tier_cents is None:
        tier_cents = (0.02, 0.03, 0.05, 0.10)

    return FillModel(
        model=model,
        cents=cents,
        pct=pct,
        fees_per_trade=fees_per_trade,
        tier_thresholds=tier_thresholds,
        tier_cents=tier_cents,
    )

