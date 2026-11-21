"""Upload the homework 3 input and four disjoint JSONL parts to RustFS."""

from contextlib import ExitStack
import hashlib
import json
from pathlib import Path

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError
from dotenv import dotenv_values


EXPECTED_ROWS = 68770
EXPECTED_SHA256 = "d9bb991e4932c95d2231decb70f21b31338c4be0a3b89cf9d1a8cbfefd20e2b5"


def file_hash(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def split_file(source, directory, row_count, part_count=4):
    directory.mkdir(parents=True, exist_ok=True)
    paths = [directory / f"part-{i}.jsonl" for i in range(part_count)]
    rows_per_part = (row_count + part_count - 1) // part_count
    counts = [0] * part_count
    with ExitStack() as stack:
        streams = [stack.enter_context(path.open("wb")) for path in paths]
        with source.open("rb") as stream:
            for i, line in enumerate(stream):
                if not line.strip() or i >= row_count:
                    raise ValueError("Unexpected blank line or extra source row")
                part = i // rows_per_part
                streams[part].write(line)
                counts[part] += 1
    if sum(counts) != row_count or any(n == 0 for n in counts):
        raise ValueError("Source row count differs from the expected value")
    combined = hashlib.sha256()
    for path in paths:
        with path.open("rb") as stream:
            while chunk := stream.read(1024 * 1024):
                combined.update(chunk)
    if combined.hexdigest() != file_hash(source):
        raise ValueError("Concatenated parts differ from the source")
    return paths, counts, combined.hexdigest()


def object_hash(client, bucket, key):
    digest = hashlib.sha256()
    body = client.get_object(Bucket=bucket, Key=key)["Body"]
    try:
        for chunk in body.iter_chunks(chunk_size=1024 * 1024):
            digest.update(chunk)
    finally:
        body.close()
    return digest.hexdigest()


def main():
    config = dotenv_values(".env")
    for name in ("S3_ENDPOINT", "S3_ACCESS_KEY", "S3_SECRET_KEY"):
        if not config.get(name):
            raise SystemExit(f"Missing {name} in .env")
    source = Path("data/it_vacancies.jsonl")
    if file_hash(source) != EXPECTED_SHA256:
        raise SystemExit("Input SHA-256 differs from homework 3")
    paths, counts, combined_hash = split_file(source, Path("data/parts"), EXPECTED_ROWS)
    region = config.get("S3_REGION") or "us-east-1"
    bucket = config.get("S3_BUCKET") or "hh-lake"
    original_key = config.get("S3_KEY") or "raw/it_vacancies.jsonl"
    client = boto3.client(
        "s3", endpoint_url=config["S3_ENDPOINT"],
        aws_access_key_id=config["S3_ACCESS_KEY"],
        aws_secret_access_key=config["S3_SECRET_KEY"], region_name=region,
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"},
                      connect_timeout=5, read_timeout=60, retries={"max_attempts": 3}),
    )
    try:
        client.head_bucket(Bucket=bucket)
    except ClientError as exc:
        if exc.response["Error"]["Code"] not in ("404", "NoSuchBucket", "NotFound"):
            raise
        kwargs = {"Bucket": bucket}
        if region != "us-east-1":
            kwargs["CreateBucketConfiguration"] = {"LocationConstraint": region}
        client.create_bucket(**kwargs)
    files = [(source, original_key, EXPECTED_ROWS)]
    files.extend((path, f"parts/{path.name}", n) for path, n in zip(paths, counts))
    records = []
    print(f"Bucket: {bucket}")
    print("KEY | ROWS | BYTES | SHA256_OK", flush=True)
    for path, key, n in files:
        digest = file_hash(path)
        client.upload_file(str(path), bucket, key, ExtraArgs={
            "ContentType": "application/x-ndjson", "Metadata": {"sha256": digest},
        })
        remote_digest = object_hash(client, bucket, key)
        size = client.head_object(Bucket=bucket, Key=key)["ContentLength"]
        if remote_digest != digest or size != path.stat().st_size:
            raise ValueError(f"S3 object verification failed: {key}")
        records.append({"key": key, "rows": n, "bytes": size,
                        "sha256": digest, "downloaded_sha256": remote_digest, "verified": True})
        print(f"{key} | {n} | {size} | True", flush=True)
    proof = {
        "endpoint": config["S3_ENDPOINT"], "bucket": bucket,
        "original_sha256": EXPECTED_SHA256, "parts_concatenated_sha256": combined_hash,
        "source_rows": EXPECTED_ROWS, "part_rows": counts, "part_rows_total": sum(counts),
        "objects": records, "all_s3_hashes_match": True,
    }
    Path("evidence").mkdir(exist_ok=True)
    Path("evidence/s3-input.json").write_text(
        json.dumps(proof, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
    )
    print(f"Rows across 4 parts: {sum(counts)}")
    print(f"Concatenated SHA-256: {combined_hash}")
    print("All S3 hashes match: True")


if __name__ == "__main__":
    main()
