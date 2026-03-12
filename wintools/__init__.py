"""WinTools package metadata."""

try:
    from ._build_version import VERSION as __version__
except Exception:
    __version__ = "0.0.0-dev"

__all__ = ["__version__"]
