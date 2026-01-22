"""Parameter sensitivity analysis and slippage stress testing."""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd
import numpy as np


@dataclass
class SensitivityResult:
    """Result from a single parameter sensitivity run."""

    param_path: tuple[str, ...]
    param_value: Any
    total_trades: int = 0
    total_pnl: float = 0.0
    win_rate: float = 0.0
    sharpe_ratio: float = 0.0
    max_drawdown_pct: float = 0.0
    expectancy: float = 0.0
    profit_factor: float = 0.0
    avg_pnl: float = 0.0

    # Slippage-specific fields
    slippage_model: str = ""
    slippage_description: str = ""

    # Permutation test results (if available)
    perm_p_value: float | None = None
    perm_significant: bool | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "param_path": list(self.param_path),
            "param_value": self.param_value,
            "total_trades": self.total_trades,
            "total_pnl": round(self.total_pnl, 2),
            "win_rate": round(self.win_rate, 4),
            "sharpe_ratio": round(self.sharpe_ratio, 4),
            "max_drawdown_pct": round(self.max_drawdown_pct, 4),
            "expectancy": round(self.expectancy, 4),
            "profit_factor": round(self.profit_factor, 4),
            "avg_pnl": round(self.avg_pnl, 4),
            "slippage_model": self.slippage_model,
            "slippage_description": self.slippage_description,
            "perm_p_value": self.perm_p_value,
            "perm_significant": self.perm_significant,
        }


@dataclass
class SensitivityAnalysis:
    """Complete sensitivity analysis results."""

    parameter_name: str
    test_values: list[Any]
    results: list[SensitivityResult] = field(default_factory=list)
    baseline_value: Any = None
    baseline_result: SensitivityResult | None = None

    def to_dataframe(self) -> pd.DataFrame:
        """Convert results to DataFrame for analysis."""
        rows = [r.to_dict() for r in self.results]
        return pd.DataFrame(rows)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "parameter_name": self.parameter_name,
            "test_values": self.test_values,
            "baseline_value": self.baseline_value,
            "results": [r.to_dict() for r in self.results],
        }

    def summary_table(self) -> str:
        """Generate a formatted summary table."""
        df = self.to_dataframe()
        if df.empty:
            return "No results"

        # Select key columns
        cols = ["param_value", "total_trades", "total_pnl", "win_rate", "sharpe_ratio", "expectancy"]
        available_cols = [c for c in cols if c in df.columns]
        return df[available_cols].to_string(index=False)


def run_sensitivity_analysis(
    config_dict: dict[str, Any],
    param_path: tuple[str, ...],
    test_values: list[Any],
    start_date: str,
    end_date: str,
    output_base_dir: Path,
    polygon_api_key: str | None = None,
) -> SensitivityAnalysis:
    """
    Run backtest with different parameter values and collect metrics.

    Args:
        config_dict: Base configuration dictionary.
        param_path: Tuple of keys to navigate to parameter (e.g., ("execution", "slippage", "cents")).
        test_values: List of values to test for this parameter.
        start_date: Backtest start date (YYYY-MM-DD).
        end_date: Backtest end date (YYYY-MM-DD).
        output_base_dir: Base directory for outputs (subdirs created per value).
        polygon_api_key: Optional API key (uses env var if not provided).

    Returns:
        SensitivityAnalysis with results for each parameter value.
    """
    # Import here to avoid circular imports
    from ybi_strategy.config import Config
    from ybi_strategy.polygon.client import PolygonClient
    from ybi_strategy.backtest.engine import BacktestEngine

    analysis = SensitivityAnalysis(
        parameter_name=".".join(param_path),
        test_values=test_values,
    )

    # Get baseline value
    node = config_dict
    for key in param_path[:-1]:
        node = node.get(key, {})
    analysis.baseline_value = node.get(param_path[-1])

    # Initialize Polygon client once
    polygon = PolygonClient(api_key=polygon_api_key)

    for value in test_values:
        # Create variant config
        variant_dict = copy.deepcopy(config_dict)

        # Navigate to the parameter and set it
        node = variant_dict
        for key in param_path[:-1]:
            if key not in node:
                node[key] = {}
            node = node[key]
        node[param_path[-1]] = value

        # Create output directory for this variant
        value_str = str(value).replace(".", "_")
        output_dir = output_base_dir / f"{param_path[-1]}_{value_str}"
        output_dir.mkdir(parents=True, exist_ok=True)

        # Run backtest
        config = Config(raw=variant_dict)
        engine = BacktestEngine(
            config=config,
            polygon=polygon,
            output_dir=output_dir,
        )
        engine.run(start_date=start_date, end_date=end_date)

        # Load results
        summary_path = output_dir / "summary.json"
        if summary_path.exists():
            summary = json.loads(summary_path.read_text())
            metrics = summary.get("metrics", {})
            neg_controls = summary.get("negative_controls", {})
            perm_sharpe = neg_controls.get("permutation_test_sharpe", {})

            result = SensitivityResult(
                param_path=param_path,
                param_value=value,
                total_trades=metrics.get("total_trades", 0),
                total_pnl=metrics.get("total_pnl", 0.0),
                win_rate=metrics.get("win_rate", 0.0),
                sharpe_ratio=metrics.get("sharpe_ratio", 0.0),
                max_drawdown_pct=metrics.get("max_drawdown_pct", 0.0),
                expectancy=metrics.get("expectancy", 0.0),
                profit_factor=metrics.get("profit_factor", 0.0),
                avg_pnl=metrics.get("avg_pnl", 0.0),
                slippage_model=engine.fills.model,
                slippage_description=engine.fills.describe(),
                perm_p_value=perm_sharpe.get("p_value_numeric"),
                perm_significant=perm_sharpe.get("is_significant_5pct"),
            )
            analysis.results.append(result)

            # Mark baseline
            if value == analysis.baseline_value:
                analysis.baseline_result = result

    return analysis


def run_slippage_stress_test(
    config_dict: dict[str, Any],
    start_date: str,
    end_date: str,
    output_base_dir: Path,
    polygon_api_key: str | None = None,
    cents_values: list[float] | None = None,
    pct_values: list[float] | None = None,
) -> dict[str, SensitivityAnalysis]:
    """
    Run comprehensive slippage stress test with multiple models.

    Args:
        config_dict: Base configuration dictionary.
        start_date: Backtest start date.
        end_date: Backtest end date.
        output_base_dir: Base directory for outputs.
        polygon_api_key: Optional API key.
        cents_values: List of fixed cents values to test (default: [0.01, 0.02, 0.05, 0.10]).
        pct_values: List of percentage values to test (default: [0.001, 0.002, 0.005, 0.01]).

    Returns:
        Dictionary with SensitivityAnalysis for each slippage model type.
    """
    if cents_values is None:
        cents_values = [0.01, 0.02, 0.05, 0.10]
    if pct_values is None:
        pct_values = [0.001, 0.002, 0.005, 0.01]  # 0.1% to 1.0%

    results = {}

    # Test fixed cents model
    cents_config = copy.deepcopy(config_dict)
    cents_config["execution"]["slippage"]["model"] = "fixed_cents"

    results["fixed_cents"] = run_sensitivity_analysis(
        config_dict=cents_config,
        param_path=("execution", "slippage", "cents"),
        test_values=cents_values,
        start_date=start_date,
        end_date=end_date,
        output_base_dir=output_base_dir / "fixed_cents",
        polygon_api_key=polygon_api_key,
    )

    # Test percentage model
    pct_config = copy.deepcopy(config_dict)
    pct_config["execution"]["slippage"]["model"] = "pct_of_price"

    results["pct_of_price"] = run_sensitivity_analysis(
        config_dict=pct_config,
        param_path=("execution", "slippage", "pct"),
        test_values=pct_values,
        start_date=start_date,
        end_date=end_date,
        output_base_dir=output_base_dir / "pct_of_price",
        polygon_api_key=polygon_api_key,
    )

    return results


def compare_results(
    results: dict[str, SensitivityAnalysis],
    output_path: Path | None = None,
) -> pd.DataFrame:
    """
    Compare results across different sensitivity analyses.

    Args:
        results: Dictionary of SensitivityAnalysis results.
        output_path: Optional path to save comparison CSV.

    Returns:
        DataFrame with all results combined.
    """
    all_rows = []

    for analysis_name, analysis in results.items():
        for result in analysis.results:
            row = result.to_dict()
            row["analysis"] = analysis_name
            row["parameter"] = analysis.parameter_name
            all_rows.append(row)

    df = pd.DataFrame(all_rows)

    if output_path and not df.empty:
        df.to_csv(output_path, index=False)

    return df


def generate_stress_test_report(
    results: dict[str, SensitivityAnalysis],
    output_path: Path,
) -> None:
    """
    Generate a markdown report summarizing stress test results.

    Args:
        results: Dictionary of SensitivityAnalysis results.
        output_path: Path to save the markdown report.
    """
    lines = [
        "# Slippage Stress Test Report",
        "",
        "## Summary",
        "",
    ]

    for analysis_name, analysis in results.items():
        lines.append(f"### {analysis_name.replace('_', ' ').title()}")
        lines.append("")

        if not analysis.results:
            lines.append("No results available.")
            lines.append("")
            continue

        # Create summary table
        lines.append("| Value | Trades | Total P&L | Win Rate | Sharpe | Expectancy |")
        lines.append("|-------|--------|-----------|----------|--------|------------|")

        for r in analysis.results:
            pnl_str = f"${r.total_pnl:,.2f}"
            wr_str = f"{r.win_rate * 100:.1f}%"
            lines.append(
                f"| {r.param_value} | {r.total_trades} | {pnl_str} | {wr_str} | "
                f"{r.sharpe_ratio:.2f} | ${r.expectancy:.2f} |"
            )

        lines.append("")

        # Compute sensitivity
        if len(analysis.results) >= 2:
            pnl_values = [r.total_pnl for r in analysis.results]
            param_values = [r.param_value for r in analysis.results]

            pnl_range = max(pnl_values) - min(pnl_values)
            best_idx = pnl_values.index(max(pnl_values))
            worst_idx = pnl_values.index(min(pnl_values))

            lines.append(f"**P&L Range**: ${pnl_range:,.2f}")
            lines.append(f"**Best**: {param_values[best_idx]} (${pnl_values[best_idx]:,.2f})")
            lines.append(f"**Worst**: {param_values[worst_idx]} (${pnl_values[worst_idx]:,.2f})")
            lines.append("")

    # Conclusions
    lines.append("## Conclusions")
    lines.append("")

    # Check if strategy is consistently unprofitable
    all_pnls = []
    for analysis in results.values():
        all_pnls.extend([r.total_pnl for r in analysis.results])

    if all_pnls:
        if all(p < 0 for p in all_pnls):
            lines.append(
                "The strategy shows **consistent negative P&L** across all slippage scenarios. "
                "This confirms the negative edge is robust to execution assumptions."
            )
        elif all(p > 0 for p in all_pnls):
            lines.append(
                "The strategy shows **consistent positive P&L** across all slippage scenarios. "
                "The edge appears robust to execution costs."
            )
        else:
            lines.append(
                "The strategy's profitability is **sensitive to slippage assumptions**. "
                "Further investigation of realistic execution costs is recommended."
            )

    lines.append("")
    lines.append("---")
    lines.append("*Generated by YBI Strategy Stress Test*")

    output_path.write_text("\n".join(lines), encoding="utf-8")
