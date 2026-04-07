# src/web/__init__.py
"""Web server for the memorial card digitizer.

Public API:
    make_server — Create and configure the HTTP server
"""

from src.web.server import make_server

__all__ = ["make_server"]
