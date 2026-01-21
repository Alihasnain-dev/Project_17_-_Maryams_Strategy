from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FillModel:
    model: str
    cents: float

    def apply_entry(self, price: float) -> float:
        if self.model == "fixed_cents":
            return price + self.cents
        raise ValueError(f"Unknown slippage model: {self.model}")

    def apply_exit(self, price: float) -> float:
        if self.model == "fixed_cents":
            return price - self.cents
        raise ValueError(f"Unknown slippage model: {self.model}")

