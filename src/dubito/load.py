from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from dubito.model import Formulation


def load_formulation_here(path: str | Path) -> Formulation:
    """Import a formulation module in the current process."""

    file_path = Path(path).resolve()
    if not file_path.is_file():
        raise FileNotFoundError(file_path)
    mod_name = f"dubito_loaded_{file_path.stem}_{abs(hash(str(file_path)))}"
    spec = importlib.util.spec_from_file_location(mod_name, file_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot import formulation from {file_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = module
    spec.loader.exec_module(module)
    factory = getattr(module, "formulation", None)
    if factory is None:
        raise AttributeError(f"{file_path} does not export formulation()")
    loaded = factory()
    if not isinstance(loaded, Formulation):
        raise TypeError(f"{file_path} formulation() did not return a Formulation")
    return loaded


def load_formulation(path: str | Path, *, sandbox: bool = True) -> Formulation:
    """Load a formulation. Default is a subprocess sandbox so native solver libs do not mix.

    CVXPY's optional HiGHS and OR-Tools' bundled HiGHS cannot share a process.
    """

    if sandbox:
        from dubito.sandbox import SandboxedFormulation

        return SandboxedFormulation(path)
    return load_formulation_here(path)
