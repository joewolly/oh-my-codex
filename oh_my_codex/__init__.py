"""Oh-My-Codex package."""

__version__ = "1.0.0"

from .lifecycle import LifecycleError, doctor, install, uninstall

__all__ = ["LifecycleError", "doctor", "install", "uninstall", "__version__"]
