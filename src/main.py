# src/main.py
from pathlib import Path
import webbrowser

from src.server import make_server


def main() -> None:
    script_dir = Path(__file__).resolve().parent.parent
    input_dir = script_dir / "input"
    output_dir = script_dir / "output"
    json_dir = output_dir / "json"

    input_dir.mkdir(exist_ok=True)
    output_dir.mkdir(exist_ok=True)
    json_dir.mkdir(exist_ok=True)

    server = make_server(json_dir, input_dir, output_dir)
    port = server.server_address[1]
    url = f"http://localhost:{port}"
    print(f"Memorial Card Digitizer running at {url}")
    print("Press Ctrl+C to stop.")
    webbrowser.open(url)
    server.serve_forever()


if __name__ == "__main__":
    main()
