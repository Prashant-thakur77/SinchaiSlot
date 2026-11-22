import os
import tempfile

import pytest

_TMP = tempfile.mkdtemp(prefix="sinchai-test-")
os.environ.setdefault("DATABASE_URL", f"sqlite:///{_TMP}/test.db")
os.environ.setdefault("LLM_PROVIDER", "rules")


@pytest.fixture(scope="session")
def seeded():
    from datetime import date

    from sinchai_api import db, seed, state

    db.reset_engine()
    seed.seed(ledger_from=date(2024, 2, 15), verbose=False)
    state.reset_state()
    return True
