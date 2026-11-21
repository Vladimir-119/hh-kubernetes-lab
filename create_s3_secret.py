"""Reuse homework 3 S3 credentials without printing them or writing a Secret file."""

import json
from pathlib import Path
import subprocess
import sys

from dotenv import dotenv_values


def main():
    source = Path(sys.argv[1])
    if not source.is_file():
        raise SystemExit(f"Environment file is missing: {source}")
    config = dotenv_values(source)
    keys = ("S3_ACCESS_KEY", "S3_SECRET_KEY")
    if any(not config.get(key) for key in keys):
        raise SystemExit("S3_ACCESS_KEY and S3_SECRET_KEY must both be set in the old .env")
    secret = {
        "apiVersion": "v1", "kind": "Secret",
        "metadata": {"name": "s3-credentials", "namespace": "hh-lab"},
        "type": "Opaque", "stringData": {key: config[key] for key in keys},
    }
    subprocess.run(
        ["kubectl", "--context=de-k8s", "-n", "hh-lab", "apply", "-f", "-"],
        input=json.dumps(secret), text=True, check=True,
    )


if __name__ == "__main__":
    main()
