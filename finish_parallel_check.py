"""Merge the four real S3 results and compare every pair with homework 3.

Run from hh-kubernetes-lab using the Python environment that ran upload_s3_data.py.
The existing .env and the RustFS port-forward must be available.
"""

from collections import Counter
import csv
import hashlib
import io
import json
import os
from pathlib import Path

from dotenv import dotenv_values

from worker import s3_client, write_counts


def parse_counts(data):
    result = Counter()
    for row in csv.DictReader(io.StringIO(data.decode("utf-8"), newline="")):
        skills = tuple(json.loads(row["skills"]))
        count = int(row["n"])
        if len(skills) != 2 or tuple(sorted(set(skills))) != skills or count <= 0:
            raise ValueError(f"Invalid pair: {row!r}")
        if skills in result:
            raise ValueError(f"Duplicate pair: {skills!r}")
        result[skills] = count
    return result


def download(client, bucket, key):
    body = client.get_object(Bucket=bucket, Key=key)["Body"]
    try:
        return body.read()
    finally:
        body.close()


def main():
    config = dotenv_values(".env")
    for name in ("S3_ENDPOINT", "S3_ACCESS_KEY", "S3_SECRET_KEY", "S3_REGION"):
        if config.get(name):
            os.environ[name] = config[name]
    for name in ("S3_ENDPOINT", "S3_ACCESS_KEY", "S3_SECRET_KEY"):
        if not os.environ.get(name):
            raise SystemExit(f"Missing {name}: run from the project folder with .env")

    reference_path = Path("reference/counts_k2.csv")
    reference_data = reference_path.read_bytes()
    reference = parse_counts(reference_data)
    proof = json.loads(Path("evidence/parallel-summary.json").read_text())
    expected = {part["index"]: part for part in proof["parts"]}
    if set(expected) != set(range(4)):
        raise SystemExit("Expected proof for all four indexes")

    client = s3_client()
    bucket = config.get("S3_BUCKET") or "hh-lake"
    parts_dir = Path("results/parts")
    parts_dir.mkdir(parents=True, exist_ok=True)
    merged = Counter()
    downloaded = []
    for index in range(4):
        key = f"results/parts/part-{index}.csv"
        data = download(client, bucket, key)
        counts = parse_counts(data)
        if (len(counts) != expected[index]["unique_pairs"]
                or sum(counts.values()) != expected[index]["sum_counts"]):
            raise SystemExit(f"S3 part {index} differs from its Kubernetes log")
        (parts_dir / f"part-{index}.csv").write_bytes(data)
        merged.update(counts)
        downloaded.append({"index": index, "key": key,
                           "sha256": hashlib.sha256(data).hexdigest(),
                           "unique_pairs": len(counts), "sum_counts": sum(counts.values())})

    ranked = sorted(merged.items(), key=lambda item: (-item[1], item[0]))
    reference_ranked = sorted(reference.items(), key=lambda item: (-item[1], item[0]))
    output_path = Path("results/parallel.csv")
    write_counts(str(output_path), ranked)
    write_counts(f"s3://{bucket}/results/merged/counts_k2.csv", ranked)
    saved_data = download(client, bucket, "results/merged/counts_k2.csv")
    if saved_data != output_path.read_bytes():
        raise SystemExit("S3 merged output differs from the local merged output")

    verification = {
        "source": "Four complete CSV files downloaded from the existing Indexed Job outputs",
        "parts": downloaded, "unique_pairs": len(merged),
        "sum_counts": sum(merged.values()),
        "full_counts_equal": merged == reference,
        "full_csv_bytes_equal": output_path.read_bytes() == reference_data,
        "top10_equal": ranked[:10] == reference_ranked[:10],
        "output_sha256": hashlib.sha256(output_path.read_bytes()).hexdigest(),
        "reference_sha256": hashlib.sha256(reference_data).hexdigest(),
        "s3_output": f"s3://{bucket}/results/merged/counts_k2.csv",
    }
    Path("evidence/parallel-verification.json").write_text(
        json.dumps(verification, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("PAIR | COUNT")
    for pair, count in ranked[:10]:
        print(f"{pair[0]} + {pair[1]} | {count}")
    print(json.dumps(verification, ensure_ascii=False, indent=2))
    if not verification["full_counts_equal"] or not verification["top10_equal"]:
        raise SystemExit("Parallel result differs from homework 3")
    print("Full parallel result and top-10 match HW3: True")


if __name__ == "__main__":
    main()
