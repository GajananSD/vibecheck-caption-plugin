import os
import sys
import tempfile
from pathlib import Path

# Must be set before the plugin modules import config.
os.environ["USE_GEMINI"] = "0"
os.environ["FETCH_POSTS"] = "0"
os.environ["PLUGIN_DB_PATH"] = os.path.join(tempfile.mkdtemp(), "test.db")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
