import logging
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from cibst.config import load_config  # noqa: E402
from cibst.pipeline import run_pipeline  # noqa: E402


@pytest.fixture(scope="session")
def cfg():
    return load_config()


@pytest.fixture(scope="session")
def small_run(tmp_path_factory):
    """A reduced end-to-end run shared across integration tests."""
    logging.getLogger("cibst").setLevel(logging.WARNING)
    out = tmp_path_factory.mktemp("runs")
    return run_pipeline(overrides={"portfolio": {"n_obligors": 400, "history_obligors_per_year": 800}},
                        out_root=str(out), run_id="pytest", sensitivities=False)
