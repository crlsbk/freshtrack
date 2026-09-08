import sys
from pathlib import Path


APP_DIR = Path(__file__).parent / "app"
sys.path.insert(0, str(APP_DIR))

from app import app


if __name__ == "__main__":
    app.run(debug=True)
