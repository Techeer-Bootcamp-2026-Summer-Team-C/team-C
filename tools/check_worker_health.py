import argparse

from backend.worker_health import WORKER_NAMES, worker_heartbeat_is_fresh


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Check whether a worker loop has recently completed an iteration.")
    parser.add_argument("worker", choices=sorted(WORKER_NAMES))
    parser.add_argument("--max-age", type=float, required=True, help="Maximum heartbeat age in seconds.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return 0 if worker_heartbeat_is_fresh(args.worker, max_age_seconds=args.max_age) else 1


if __name__ == "__main__":
    raise SystemExit(main())
