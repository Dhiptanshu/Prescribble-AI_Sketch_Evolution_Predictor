"""Shared constants. Everything lives in a fixed 256x256 QuickDraw frame."""
import os
from pathlib import Path

from src.classsets import CLASS_SETS

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"
PROC_DIR = ROOT / "data" / "processed"
RUNS_DIR = ROOT / "runs"

# The class list of the model generation being worked on: PRESCRIBBLE_CLASS_SET=v1 (default, 30 classes) or v2 (100). See src/classsets.py.
CLASS_SET = os.environ.get("PRESCRIBBLE_CLASS_SET", "v1")
CLASSES = CLASS_SETS[CLASS_SET]
DATA_DIR = PROC_DIR if CLASS_SET == "v1" else PROC_DIR / CLASS_SET      # sketches.pkl and the evaluation caches of this class set
SET_RUNS = RUNS_DIR if CLASS_SET == "v1" else RUNS_DIR / CLASS_SET      # trained checkpoints and results of this class set
NUM_CLASSES = len(CLASSES)

FRAME = 255.0          # coordinates are 0..255
IMG = 64               # raster size
THICKNESS = 2          # line thickness in raster pixels
MAX_PTS = 128          # max points fed to the sequence branch
SEQ_FEATS = 5          # x, y, dx, dy, new_stroke
EVAL_FRACS = [0.1, 0.2, 0.3, 0.5, 0.75, 1.0]
