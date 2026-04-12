"""Tests for docs/ai/rebuild.py."""

import textwrap
from pathlib import Path

import pytest

# rebuild.py lives outside src/, so we import it by path
import importlib.util

_REBUILD_PATH = Path(__file__).resolve().parent.parent / "docs" / "ai" / "rebuild.py"

@pytest.fixture
def rebuild():
    spec = importlib.util.spec_from_file_location("rebuild", _REBUILD_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_build_file_tree(rebuild, tmp_path):
    """build_file_tree returns a sorted list of (relative_path, description) tuples."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "__init__.py").write_text("")
    pkg = src / "foo"
    pkg.mkdir()
    (pkg / "__init__.py").write_text('"""Foo package."""\n')
    (pkg / "bar.py").write_text('"""Bar module — does bar things."""\n\ndef hello(): pass\n')

    tree = rebuild.build_file_tree(src)
    assert ("foo/__init__.py", "Foo package.") in tree
    assert ("foo/bar.py", "Bar module — does bar things.") in tree


def test_get_package_exports(rebuild, tmp_path):
    """get_package_exports returns exports from __init__.py __all__."""
    pkg = tmp_path / "mypkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text(textwrap.dedent('''\
        """My package."""
        from mypkg.core import do_thing
        __all__ = ["do_thing"]
    '''))
    (pkg / "core.py").write_text(textwrap.dedent('''\
        def do_thing(x: int, y: str = "hi") -> bool:
            """Check if x is valid."""
            return True
    '''))

    exports = rebuild.get_package_exports(pkg)
    assert len(exports) == 1
    assert exports[0]["name"] == "do_thing"
    assert "x: int" in exports[0]["signature"]
    assert exports[0]["docstring"] == "Check if x is valid."


def test_extract_routes(rebuild, tmp_path):
    """extract_routes parses route patterns from server.py-style code."""
    server_py = tmp_path / "server.py"
    server_py.write_text(textwrap.dedent('''\
        class Handler:
            def do_GET(self):
                if self.path == "/":
                    pass
                elif self.path == "/api/cards":
                    pass
                elif self.path.startswith("/api/cards/"):
                    pass
            def do_POST(self):
                if self.path == "/api/export":
                    pass
            def do_PUT(self):
                if self.path.startswith("/api/cards/"):
                    pass
    '''))

    routes = rebuild.extract_routes(server_py)
    assert ("GET", "/") in routes
    assert ("GET", "/api/cards") in routes
    assert ("GET", "/api/cards/:id") in routes
    assert ("POST", "/api/export") in routes
    assert ("PUT", "/api/cards/:id") in routes


def test_generate_architecture(rebuild, tmp_path):
    """generate_architecture produces markdown with file tree and routes."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "__init__.py").write_text("")
    web = src / "web"
    web.mkdir()
    (web / "__init__.py").write_text('"""Web server."""\n')
    (web / "server.py").write_text(textwrap.dedent('''\
        """HTTP server."""
        class Handler:
            def do_GET(self):
                if self.path == "/api/cards":
                    pass
    '''))

    md = rebuild.generate_architecture(src)
    assert "## File Tree" in md
    assert "web/server.py" in md
    assert "## HTTP API Endpoints" in md
    assert "GET" in md
    assert "/api/cards" in md


def test_generate_api_surface(rebuild, tmp_path):
    """generate_api_surface produces markdown with function signatures per package."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "__init__.py").write_text("")
    pkg = src / "tools"
    pkg.mkdir()
    (pkg / "__init__.py").write_text(textwrap.dedent('''\
        """Tool utilities."""
        from tools.hammer import hit
        __all__ = ["hit"]
    '''))
    (pkg / "hammer.py").write_text(textwrap.dedent('''\
        def hit(nail: str, force: int = 10) -> bool:
            """Drive a nail with given force."""
            return True
    '''))

    # Also test standalone modules
    (src / "helper.py").write_text(textwrap.dedent('''\
        """Helper functions."""

        def greet(name: str) -> str:
            """Say hello."""
            return f"Hello {name}"
    '''))

    md = rebuild.generate_api_surface(src)
    assert "## tools" in md
    assert "hit(nail: str, force: int = 10) -> bool" in md
    assert "Drive a nail with given force." in md
    assert "## Standalone Modules" in md
    assert "greet(name: str) -> str" in md


def test_generate_data_model(rebuild, tmp_path):
    """generate_data_model extracts PERSON_SCHEMA and documents directory layout."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "__init__.py").write_text("")
    extraction = src / "extraction"
    extraction.mkdir()
    (extraction / "__init__.py").write_text("")
    (extraction / "schema.py").write_text(textwrap.dedent('''\
        PERSON_SCHEMA = {
            "type": "object",
            "properties": {
                "person": {
                    "type": "object",
                    "properties": {
                        "first_name": {"type": "string"},
                    },
                },
            },
        }
    '''))

    # Create directory structure
    (tmp_path / "input").mkdir()
    (tmp_path / "output" / "json").mkdir(parents=True)
    (tmp_path / "output" / "text").mkdir()
    (tmp_path / "output" / "export").mkdir()

    md = rebuild.generate_data_model(src)
    assert "## PERSON_SCHEMA" in md
    assert "first_name" in md
    assert "## Directory Layout" in md
    assert "input/" in md
    assert "output/json/" in md


def test_rebuild_creates_three_files(rebuild, tmp_path):
    """rebuild_all creates architecture.md, api-surface.md, data-model.md."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "__init__.py").write_text("")
    pkg = src / "extraction"
    pkg.mkdir()
    (pkg / "__init__.py").write_text('"""Extraction pipeline."""\n__all__ = []\n')
    (pkg / "schema.py").write_text('PERSON_SCHEMA = {"type": "object", "properties": {}}\n')
    (tmp_path / "input").mkdir()
    (tmp_path / "output" / "json").mkdir(parents=True)

    ai_dir = tmp_path / "docs" / "ai"
    ai_dir.mkdir(parents=True)

    rebuild.rebuild_all(src, ai_dir)

    assert (ai_dir / "architecture.md").exists()
    assert (ai_dir / "api-surface.md").exists()
    assert (ai_dir / "data-model.md").exists()

    content = (ai_dir / "architecture.md").read_text()
    assert "AUTO-GENERATED" in content


def test_rebuild_quiet_no_output_when_unchanged(rebuild, tmp_path, capsys):
    """In quiet mode, rebuild produces no output when files haven't changed."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "__init__.py").write_text("")
    pkg = src / "extraction"
    pkg.mkdir()
    (pkg / "__init__.py").write_text('"""Extraction."""\n__all__ = []\n')
    (pkg / "schema.py").write_text('PERSON_SCHEMA = {"type": "object", "properties": {}}\n')
    (tmp_path / "input").mkdir()

    ai_dir = tmp_path / "docs" / "ai"
    ai_dir.mkdir(parents=True)

    # First run writes files
    rebuild.rebuild_all(src, ai_dir, quiet=True)
    capsys.readouterr()  # clear

    # Second run: nothing changed
    rebuild.rebuild_all(src, ai_dir, quiet=True)
    captured = capsys.readouterr()
    assert captured.out == ""
