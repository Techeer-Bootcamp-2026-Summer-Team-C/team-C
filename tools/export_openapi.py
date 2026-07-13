import argparse
import json
from pathlib import Path

from backend.main import app

ROOT = Path(__file__).parents[1]
DEFAULT_OUTPUT = ROOT / "openapi/openapi.json"


def render_openapi() -> str:
    return json.dumps(app.openapi(), ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export the deterministic FastAPI OpenAPI document.")
    parser.add_argument("--check", action="store_true", help="Fail when the checked-in artifact is stale.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    arguments = parse_args(argv)
    rendered = render_openapi()
    if arguments.check:
        if not arguments.output.exists() or arguments.output.read_text(encoding="utf-8") != rendered:
            print(f"OpenAPI artifact is stale: {arguments.output}")
            return 1
        print(f"OpenAPI artifact is current: {arguments.output}")
        return 0
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(rendered, encoding="utf-8")
    print(f"Exported OpenAPI artifact: {arguments.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
