# tests/test_static.py
"""Tests for static file serving."""

from pathlib import Path
from threading import Thread
from urllib.error import HTTPError
from urllib.request import urlopen

import pytest


def _start_test_server(json_dir, input_dir, output_dir, port=0):
    from src.web.server import make_server
    server = make_server(json_dir, input_dir, output_dir, port=port)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    actual_port = server.server_address[1]
    return server, f"http://localhost:{actual_port}"


def test_static_css_served_with_correct_type(tmp_path):
    json_dir = tmp_path / "json"
    json_dir.mkdir()
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    server, base = _start_test_server(json_dir, input_dir, output_dir)
    try:
        resp = urlopen(f"{base}/static/style.css")
        assert resp.status == 200
        assert "text/css" in resp.headers.get("Content-Type", "")
        body = resp.read().decode()
        assert "nav-bar" in body
    finally:
        server.shutdown()


def test_static_js_served_with_correct_type(tmp_path):
    json_dir = tmp_path / "json"
    json_dir.mkdir()
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    server, base = _start_test_server(json_dir, input_dir, output_dir)
    try:
        resp = urlopen(f"{base}/static/app.js")
        assert resp.status == 200
        content_type = resp.headers.get("Content-Type", "")
        assert "javascript" in content_type or "text/plain" in content_type
        body = resp.read().decode()
        assert "showSection" in body
    finally:
        server.shutdown()


def test_static_nonexistent_returns_404(tmp_path):
    json_dir = tmp_path / "json"
    json_dir.mkdir()
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    server, base = _start_test_server(json_dir, input_dir, output_dir)
    try:
        with pytest.raises(HTTPError) as exc_info:
            urlopen(f"{base}/static/nonexistent.css")
        assert exc_info.value.code == 404
    finally:
        server.shutdown()


def test_static_path_traversal_returns_403(tmp_path):
    json_dir = tmp_path / "json"
    json_dir.mkdir()
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    server, base = _start_test_server(json_dir, input_dir, output_dir)
    try:
        with pytest.raises(HTTPError) as exc_info:
            urlopen(f"{base}/static/..%2F..%2Fconfig.json")
        assert exc_info.value.code == 403
    finally:
        server.shutdown()


def test_root_serves_index_html(tmp_path):
    json_dir = tmp_path / "json"
    json_dir.mkdir()
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    server, base = _start_test_server(json_dir, input_dir, output_dir)
    try:
        resp = urlopen(f"{base}/")
        body = resp.read().decode()
        assert "<!DOCTYPE html>" in body
        assert 'href="/static/style.css"' in body
        assert 'src="/static/app.js"' in body
    finally:
        server.shutdown()
