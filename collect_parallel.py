"""Save real per-index Kubernetes logs and check that all input parts finished."""

from datetime import datetime
import json
from pathlib import Path
import subprocess


BASE = ["kubectl", "--context=de-k8s", "-n", "hh-lab"]


def kubectl(*args):
    return subprocess.check_output([*BASE, *args], text=True)


def main():
    logs, evidence = Path("logs"), Path("evidence")
    logs.mkdir(exist_ok=True)
    evidence.mkdir(exist_ok=True)
    pod_text = kubectl("get", "pods", "-l", "job-name=pairs-parallel", "-o", "json")
    pods = json.loads(pod_text)["items"]
    (evidence / "parallel-pods.json").write_text(pod_text, encoding="utf-8")
    part_proof = json.loads((evidence / "s3-input.json").read_text(encoding="utf-8"))
    records = []
    for pod in pods:
        name = pod["metadata"]["name"]
        index = int(pod["metadata"]["annotations"]["batch.kubernetes.io/job-completion-index"])
        if pod["status"]["phase"] != "Succeeded":
            raise SystemExit(f"Pod {name} has not succeeded")
        raw = kubectl("logs", name)
        (logs / f"34-part-{index}.log").write_text(raw, encoding="utf-8")
        decoder = json.JSONDecoder()
        start, position = decoder.raw_decode(raw.lstrip())
        summary = json.loads(raw.lstrip()[position:].strip())
        if (start["job_index"] != str(index)
                or summary["inputs"] != [f"s3://hh-lake/parts/part-{index}.jsonl"]
                or summary["output"] != f"s3://hh-lake/results/parts/part-{index}.csv"
                or summary["source_rows"] != part_proof["part_rows"][index]):
            raise SystemExit(f"Input/output or row count mismatch for index {index}")
        timestamped = kubectl("logs", name, "--timestamps=true")
        (logs / f"34-part-{index}-timestamps.log").write_text(timestamped, encoding="utf-8")
        lines = [line for line in timestamped.splitlines() if line.strip()]
        started = lines[0].split(" ", 1)[0]
        finished = lines[-1].split(" ", 1)[0]
        records.append({"index": index, "pod": name, "worker_log_start": started,
                        "worker_log_finish": finished, **summary})
    records.sort(key=lambda record: record["index"])
    if [record["index"] for record in records] != [0, 1, 2, 3]:
        raise SystemExit("Expected exactly one successful Pod for each index 0,1,2,3")
    totals = {key: sum(record[key] for record in records)
              for key in ("source_rows", "selected_rows", "sum_counts")}
    if totals != {"source_rows": 68770, "selected_rows": 869, "sum_counts": 13468}:
        raise SystemExit(f"Totals differ from homework 3: {totals}")
    events = []
    for record in records:
        for key, delta in (("worker_log_start", 1), ("worker_log_finish", -1)):
            events.append((datetime.fromisoformat(record[key].replace("Z", "+00:00")), delta))
    active = peak_concurrency = 0
    for _, delta in sorted(events):
        active += delta
        peak_concurrency = max(peak_concurrency, active)
    peak_memory = max(record["peak_cgroup_mib"] for record in records)
    proof = {"job": "pairs-parallel", "configured_parallelism": 2,
             "observed_peak_concurrency": peak_concurrency,
             "concurrency_metric": "Overlap between first and last worker stdout timestamps (microsecond precision)",
             "max_peak_cgroup_mib": peak_memory, "totals": totals, "parts": records}
    (evidence / "parallel-summary.json").write_text(
        json.dumps(proof, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
    )
    print("INDEX | ROWS | SELECTED | PAIR_OCCURRENCES | PEAK_CGROUP_MIB")
    for record in records:
        print(f"{record['index']} | {record['source_rows']} | {record['selected_rows']} | "
              f"{record['sum_counts']} | {record['peak_cgroup_mib']}")
    print(f"Total rows: {totals['source_rows']}")
    print(f"Total selected vacancies: {totals['selected_rows']}")
    print(f"Total pair occurrences: {totals['sum_counts']}")
    print(f"Max concurrent workers observed: {peak_concurrency}")
    print(f"Max container memory peak: {peak_memory} MiB")
    print("All four indexes completed; partial totals match HW3: True")


if __name__ == "__main__":
    main()
