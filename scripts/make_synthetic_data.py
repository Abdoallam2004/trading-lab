"""Write random synthetic data to a separate folder, to try the pipeline offline.

    python scripts/make_synthetic_data.py --data-dir data_synthetic
    python scripts/run_backtest.py --data-dir data_synthetic
Results are meaningless for trading; the report is watermarked.
"""
import argparse
from pathlib import Path

import _bootstrap  # noqa: F401
from lab.synthetic import write_synthetic

p = argparse.ArgumentParser()
p.add_argument("--data-dir", type=Path, default=Path("data_synthetic"))
args = p.parse_args()
print("wrote", write_synthetic(args.data_dir), "->", args.data_dir)
