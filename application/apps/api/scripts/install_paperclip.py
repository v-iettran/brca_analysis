"""Install the Paperclip literature SDK into the public image.

The vendor serves a genuine, pure-Python wheel, but at a URL whose filename pip
refuses:

    gxl-paperclip @ https://paperclip.gxl.ai/paperclip.whl
    ERROR: paperclip.whl is not a valid wheel filename.

A wheel's filename is not decorative -- pip reads the package name, version and
compatibility tags straight out of it, so it has to look like
``gxl_paperclip-0.7.38-py3-none-any.whl``. ``paperclip.whl`` says nothing, and pip
stops before it ever opens the file.

The fix is only bookkeeping: download the wheel, read the name and version out of
the metadata it already carries inside, and write it back out under the name that
metadata implies. Nothing is patched or repackaged.

Failure here is deliberately not fatal. Losing literature search costs one panel,
which then states plainly that the SDK is unavailable; failing the build would cost
the entire site. Pass --strict to reverse that for local checks.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

DEFAULT_URL = "https://paperclip.gxl.ai/paperclip.whl"
TIMEOUT_SECONDS = 120


def wheel_name(archive: Path) -> str:
    """The PEP 427 filename this wheel should have, from its own metadata."""
    with zipfile.ZipFile(archive) as zf:
        dist_info = next(
            (n for n in zf.namelist() if n.endswith(".dist-info/METADATA")), None
        )
        if dist_info is None:
            raise ValueError("no .dist-info/METADATA inside; not a wheel")
        # `gxl_paperclip-0.7.38.dist-info/METADATA` already encodes name and version.
        stem = dist_info.split("/", 1)[0].removesuffix(".dist-info")
        tag = "py3-none-any"
        wheel_meta = zf.read(dist_info.replace("METADATA", "WHEEL")).decode()
        for line in wheel_meta.splitlines():
            if line.startswith("Tag:"):
                tag = line.split(":", 1)[1].strip()
                break
    return f"{stem}-{tag}.whl"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default=DEFAULT_URL)
    ap.add_argument("--strict", action="store_true", help="exit non-zero on failure")
    ap.add_argument("--dry-run", action="store_true", help="download and name it, but do not install")
    args = ap.parse_args()

    try:
        with tempfile.TemporaryDirectory() as tmp:
            raw = Path(tmp) / "download.zip"
            with urllib.request.urlopen(args.url, timeout=TIMEOUT_SECONDS) as r:
                raw.write_bytes(r.read())

            target = Path(tmp) / wheel_name(raw)
            raw.rename(target)
            print(f"Paperclip wheel resolved to {target.name}")

            if args.dry_run:
                return 0
            subprocess.run(
                [sys.executable, "-m", "pip", "install", "--no-cache-dir", str(target)],
                check=True,
            )
            print(f"Paperclip SDK installed ({target.name})")
        return 0
    except Exception as exc:  # noqa: BLE001 - any failure degrades the same way
        print(
            f"WARNING: could not install the Paperclip SDK ({type(exc).__name__}: {exc}).\n"
            "         The literature panel will report that it is unavailable.",
            file=sys.stderr,
        )
        return 1 if args.strict else 0


if __name__ == "__main__":
    raise SystemExit(main())
