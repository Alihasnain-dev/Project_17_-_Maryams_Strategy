#!/usr/bin/env python3
"""
Run slippage stress tests on the YBI strategy.

Usage:
    python scripts/run_stress_test.py --start 2024-10-01 --end 2025-01-15 --output data/stress_test

This script tests the strategy with various slippage assumptions:
- Fixed cents: 0.01, 0.02, 0.05, 0.10 per share
- Percentage: 0.1%, 0.2%, 0.5%, 1.0% of price
"""

import argparse
import json
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

from ybi_strategy.config import load_config
from ybi_strategy.analysis.sensitivity import (
    run_slippage_stress_test,
    compare_results,
    generate_stress_test_report,
)


def main():
    parser = argparse.ArgumentParser(description="Run slippage stress tests")
    parser.add_argument("--config", default="configs/strategy.yaml", help="Path to config file")
    parser.add_argument("--start", required=True, help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end", required=True, help="End date (YYYY-MM-DD)")
    parser.add_argument("--output", required=True, help="Output directory")
    parser.add_argument(
        "--cents",
        nargs="+",
        type=float,
        default=[0.01, 0.02, 0.05, 0.10],
        help="Fixed cents values to test",
    )
    parser.add_argument(
        "--pct",
        nargs="+",
        type=float,
        default=[0.001, 0.002, 0.005, 0.01],
        help="Percentage values to test (e.g., 0.001 = 0.1%%)",
    )
    args = parser.parse_args()

    # Load base config
    config_path = project_root / args.config
    config = load_config(str(config_path))

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Running slippage stress test")
    print(f"  Config: {config_path}")
    print(f"  Date range: {args.start} to {args.end}")
    print(f"  Output: {output_dir}")
    print(f"  Fixed cents values: {args.cents}")
    print(f"  Percentage values: {args.pct}")
    print()

    # Run stress tests
    results = run_slippage_stress_test(
        config_dict=config.raw,
        start_date=args.start,
        end_date=args.end,
        output_base_dir=output_dir,
        cents_values=args.cents,
        pct_values=args.pct,
    )

    # Save comparison
    comparison_df = compare_results(results, output_dir / "comparison.csv")
    print("\nComparison saved to:", output_dir / "comparison.csv")

    # Generate report
    generate_stress_test_report(results, output_dir / "stress_test_report.md")
    print("Report saved to:", output_dir / "stress_test_report.md")

    # Save raw results
    results_dict = {name: analysis.to_dict() for name, analysis in results.items()}
    with open(output_dir / "stress_test_results.json", "w") as f:
        json.dump(results_dict, f, indent=2)

    # Print summary
    print("\n" + "=" * 60)
    print("STRESS TEST SUMMARY")
    print("=" * 60)

    for name, analysis in results.items():
        print(f"\n{name.upper().replace('_', ' ')}:")
        print("-" * 40)
        for r in analysis.results:
            pnl_color = "" if r.total_pnl >= 0 else ""
            print(f"  {r.param_value:>8}: P&L=${r.total_pnl:>10,.2f}  WR={r.win_rate*100:5.1f}%  Sharpe={r.sharpe_ratio:>6.2f}")

    print("\n" + "=" * 60)


if __name__ == "__main__":
    main()
