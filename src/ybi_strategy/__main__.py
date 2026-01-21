from __future__ import annotations

import argparse
from pathlib import Path

from ybi_strategy.backtest.engine import BacktestEngine
from ybi_strategy.config import load_config
from ybi_strategy.polygon.client import PolygonClient


def main() -> int:
    parser = argparse.ArgumentParser(prog="ybi_strategy", description="YBI strategy backtest (MVP).")
    parser.add_argument("--config", default="configs/strategy.yaml")
    parser.add_argument("--start", required=True, help="YYYY-MM-DD")
    parser.add_argument("--end", required=True, help="YYYY-MM-DD")
    parser.add_argument("--out", default="data/results", help="Output directory")
    args = parser.parse_args()

    config = load_config(Path(args.config))
    client = PolygonClient.from_env()
    engine = BacktestEngine(config=config, polygon=client, output_dir=Path(args.out))
    engine.run(start_date=args.start, end_date=args.end)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

