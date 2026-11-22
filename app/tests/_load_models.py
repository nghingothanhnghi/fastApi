"""Import every `app.**.models` module so all SQLAlchemy relationships resolve.

Needed when these tests run alone (e.g. `pytest app/tests/test_payments_bank_accounts.py`):
User has relationships to models (HydroDevice, ...) that nothing else imports in that case.
"""
import importlib
import pkgutil

import app


def load_all_models() -> None:
    for mod in pkgutil.walk_packages(app.__path__, "app."):
        parts = mod.name.split(".")
        if "models" in parts and "tests" not in parts:
            try:
                importlib.import_module(mod.name)
            except Exception:  # a broken optional module must not hide the real test result
                continue


load_all_models()
