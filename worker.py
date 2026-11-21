"""Count C/C++ skill pairs using the selection rules from homework 3."""

import argparse
from collections import Counter
import csv
import io
from itertools import combinations
import json
import os
from pathlib import Path
import resource
import sys
from urllib.parse import urlsplit

from source_tools import is_variant


def s3_client():
    import boto3
    from botocore.config import Config

    return boto3.client(
        "s3",
        endpoint_url=os.environ["S3_ENDPOINT"],
        aws_access_key_id=os.environ["S3_ACCESS_KEY"],
        aws_secret_access_key=os.environ["S3_SECRET_KEY"],
        region_name=os.getenv("S3_REGION", "us-east-1"),
        config=Config(
            signature_version="s3v4", s3={"addressing_style": "path"},
            connect_timeout=5, read_timeout=60, retries={"max_attempts": 3},
        ),
    )


def s3_location(uri):
    parsed = urlsplit(uri)
    if not parsed.netloc or not parsed.path.lstrip("/"):
        raise ValueError(f"Expected s3://bucket/key, got {uri!r}")
    return parsed.netloc, parsed.path.lstrip("/")


def read_lines(uri):
    if uri.startswith("s3://"):
        bucket, key = s3_location(uri)
        body = s3_client().get_object(Bucket=bucket, Key=key)["Body"]
        try:
            for line in body.iter_lines(chunk_size=64 * 1024, keepends=True):
                yield line.decode("utf-8")
        finally:
            body.close()
    else:
        with Path(uri).open(encoding="utf-8", newline="") as stream:
            yield from stream


def write_counts(uri, ranked):
    stream = io.StringIO(newline="")
    writer = csv.writer(stream)
    writer.writerow(["skills", "n"])
    for skills, n in ranked:
        writer.writerow([json.dumps(skills, ensure_ascii=False), n])
    data = stream.getvalue().encode("utf-8")
    if uri.startswith("s3://"):
        bucket, key = s3_location(uri)
        s3_client().put_object(
            Bucket=bucket, Key=key, Body=data, ContentType="text/csv; charset=utf-8",
        )
    else:
        target = Path(uri)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)


def memory_metrics():
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    divisor = 2**20 if sys.platform == "darwin" else 1024
    result = {"peak_rss_mib": round(rss / divisor, 3)}
    peak_file = Path("/sys/fs/cgroup/memory.peak")
    if peak_file.is_file():
        result["peak_cgroup_mib"] = round(int(peak_file.read_text()) / 2**20, 3)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["count", "merge"])
    parser.add_argument("--input", nargs="+", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    index = os.getenv("JOB_COMPLETION_INDEX", "0")
    inputs = [uri.replace("{index}", index) for uri in args.input]
    output = args.output.replace("{index}", index)
    print(json.dumps({"event": "start", "command": args.command, "inputs": inputs,
                      "output": output, "job_index": index}), flush=True)
    counts = Counter()
    source_rows = selected_rows = 0
    for uri in inputs:
        if args.command == "count":
            for line in read_lines(uri):
                if not line.strip():
                    continue
                row = json.loads(line)
                source_rows += 1
                if not is_variant(row):
                    continue
                selected_rows += 1
                skills = sorted({s.strip().lower() for s in row["key_skills"] if s.strip()})
                counts.update(combinations(skills, 2))
        else:
            for row in csv.DictReader(read_lines(uri)):
                skills, n = tuple(json.loads(row["skills"])), int(row["n"])
                if len(skills) != 2 or tuple(sorted(set(skills))) != skills or n <= 0:
                    raise ValueError(f"Invalid partial result in {uri}")
                counts[skills] += n
    ranked = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    write_counts(output, ranked)
    summary = {"event": "complete", "command": args.command, "inputs": inputs,
               "output": output, "unique_pairs": len(counts), "sum_counts": sum(counts.values()),
               "top10": [{"skills": list(skills), "n": n} for skills, n in ranked[:10]]}
    if args.command == "count":
        summary.update(source_rows=source_rows, selected_rows=selected_rows)
    summary.update(memory_metrics())
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
