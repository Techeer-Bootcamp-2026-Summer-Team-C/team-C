#!/usr/bin/env python3
"""Pin service image references to a git commit SHA for production deploy.

The main-branch compose keeps ``${EDR_IMAGE_TAG:?...}`` so it stays usable with a
manually supplied tag. For GitOps auto-deploy we need the ``production`` branch to
carry an immutable image reference that Portainer polling can detect and redeploy,
so this rewrites the two image placeholders to a concrete SHA. Secret placeholders
(``${EDR_JWT_SECRET:?...}`` etc.) are intentionally left untouched and stay sourced
from Portainer stack environment variables.
"""
import sys
from pathlib import Path

PLACEHOLDER = "${EDR_IMAGE_TAG:?EDR_IMAGE_TAG is required}"
EXPECTED = 2  # backend anchor + nginx image line


def main() -> int:
    if len(sys.argv) != 2 or not sys.argv[1].strip():
        print("usage: pin-images.py <git-sha>", file=sys.stderr)
        return 2

    sha = sys.argv[1].strip()
    path = Path(__file__).with_name("compose.service.yaml")
    text = path.read_text(encoding="utf-8")

    found = text.count(PLACEHOLDER)
    if found != EXPECTED:
        print(
            f"ERROR: expected {EXPECTED} EDR_IMAGE_TAG placeholders in {path.name}, "
            f"found {found}. Aborting so a silent mis-pin cannot ship.",
            file=sys.stderr,
        )
        return 1

    path.write_text(text.replace(PLACEHOLDER, sha), encoding="utf-8")
    print(f"Pinned {EXPECTED} image references in {path.name} to {sha}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
