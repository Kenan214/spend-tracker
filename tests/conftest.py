"""Every module under src/spend_tracker imports its siblings with bare
names (`import db`, `import bills as bills_module`, ...), not as a
`spend_tracker` package — that's what lets app.py run standalone via
`streamlit run src/spend_tracker/app.py`, which puts the script's own
directory on sys.path. Tests need the same thing done explicitly.
"""
import sys
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parents[1] / "src" / "spend_tracker"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))
