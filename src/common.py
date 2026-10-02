"""Shared constants. Everything lives in a fixed 256x256 QuickDraw frame."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"
PROC_DIR = ROOT / "data" / "processed"
RUNS_DIR = ROOT / "runs"

# (display name, quickdraw file name)
CLASSES = [
    "cat", "dog", "house", "sun", "flower", "tree", "car", "bicycle", "airplane", "fish",
    "bird", "apple", "banana", "umbrella", "clock", "star", "moon", "coffee cup", "chair", "table",
    "guitar", "envelope", "key", "light bulb", "mushroom", "butterfly", "snowman", "pizza",
    "smiley face", "ice cream",
]
NUM_CLASSES = len(CLASSES)

FRAME = 255.0          # coordinates are 0..255
IMG = 64               # raster size
THICKNESS = 2          # line thickness in raster pixels
MAX_PTS = 128          # max points fed to the sequence branch
SEQ_FEATS = 5          # x, y, dx, dy, new_stroke
EVAL_FRACS = [0.1, 0.2, 0.3, 0.5, 0.75, 1.0]
