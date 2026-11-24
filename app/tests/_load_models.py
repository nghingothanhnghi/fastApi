"""Import every `app.**.models` module so all SQLAlchemy relationships resolve.

Needed when these tests run alone (e.g. `pytest app/tests/test_payments_bank_accounts.py`):
User has relationships to models (HydroDevice, ...) that nothing else imports in that case.

Modules are discovered from the file system, not pkgutil.walk_packages, because some
packages (e.g. app/hydro_system) have no __init__.py and walk_packages skips them.
"""
import importlib
from pathlib import Path

import app

_APP_DIR = Path(app.__file__).resolve().parent if getattr(app, "__file__", None) else Path(list(app.__path__)[0])


def load_all_models() -> None:
    for path in sorted(_APP_DIR.rglob("*.py")):
        rel = path.relative_to(_APP_DIR).with_suffix("")
        parts = ("app", *rel.parts)
        if "models" not in parts[:-1] or "tests" in parts or path.stem == "__init__":
            continue
        try:
            importlib.import_module(".".join(parts))
        except Exception:  # a broken optional module must not hide the real test result
            continue


load_all_models()
