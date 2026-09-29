"""Test setup for the standalone ChatOps bot package."""

from pathlib import Path
import sys


CHATOPS_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CHATOPS_ROOT))
