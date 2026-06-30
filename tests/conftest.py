import sys
from pathlib import Path

# Make the src/ package importable in tests without installation.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
