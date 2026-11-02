"""Run the deterministic local ingestion pipeline to generate sample records."""

from __future__ import annotations

import json

from crawltech.main import run_pipeline


def main() -> None:
    """Print the generated run summary as JSON."""
    print(json.dumps(run_pipeline().__dict__, sort_keys=True))


if __name__ == "__main__":
    main()
