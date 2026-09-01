"""Core configuration — edit these variables, no CLI args."""

from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = APP_DIR / "data"

CLEAN_PARQUET = DATA_DIR / "aws_clean_baseline.parquet"
EVAL_PARQUET = DATA_DIR / "aws_evaluation_dataset.parquet"

# Which dataset to replay: "clean" or "eval"
DATASET = "eval"

# How many rows to evaluate (keep small for quick runs)
ROW_LIMIT = 20

# Test layer: run L1+L2 against the eval ground-truth labels.
# TEST_ROW_LIMIT caps the window so the run stays fast.
RUN_TEST = True
TEST_ROW_LIMIT = 5000

# Forecasting layer (L4) in the test layer. Needs the Chronos-2 model
# (first run downloads ~1-2 GB from Hugging Face) and is slow on CPU,
# so FORECAST_LIMIT caps how many sliding windows we score.
RUN_FORECAST = True
FORECAST_LIMIT = 200