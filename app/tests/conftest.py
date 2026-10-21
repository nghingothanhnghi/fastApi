# app/tests/conftest.py
# app.database / app.core.config validate their environment at import time, so the defaults
# must exist before ANY test module imports app code (test files import app.payments.* before
# they get to the shared test kit). Real values from the environment or .env still win.
import os
import tempfile

os.environ.setdefault("DATABASE_URL", f"sqlite:///{tempfile.gettempdir()}/app_tests_import.db")
os.environ.setdefault("OPENAI_API_KEY", "test")
os.environ.setdefault("SECRET_KEY", "test")
