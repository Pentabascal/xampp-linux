import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import pytest

from xampp.config import Paths


@pytest.fixture
def paths(tmp_path):
    return Paths.at(tmp_path / "xampp", tmp_path / "units")
