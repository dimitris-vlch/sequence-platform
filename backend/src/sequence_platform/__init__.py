"""Sequence Platform backend package.

Layers: ``api`` (HTTP), ``database`` (external sequence archives), and
``analysis`` (pure, deterministic sequence calculations). See the
project README for the layering rules.
"""

__all__ = ["__version__", "config", "main"]
__version__ = "0.1.0"
