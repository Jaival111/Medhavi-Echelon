"""Import shim that loads Layer 0 from the repository root folder."""

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[3]
_LAYER0_FILE = _ROOT / "layer 0" / "control_plane.py"

if not _LAYER0_FILE.exists():
	raise ImportError(f"Layer 0 implementation not found at {_LAYER0_FILE}")

_SPEC = spec_from_file_location("repo_layer0_control_plane", _LAYER0_FILE)
if _SPEC is None or _SPEC.loader is None:
	raise ImportError(f"Failed to load module spec from {_LAYER0_FILE}")

_MODULE = module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)

ControlPlaneLayer = _MODULE.ControlPlaneLayer

__all__ = ["ControlPlaneLayer"]
