"""JSONL subprocess client for gnsdk-batch; it intentionally needs no shared library."""

import json
import math
import os
import subprocess
import tempfile
from typing import Iterable, Iterator, Mapping


def _process_timeout_s(job_count: int, workers: int, per_operation_timeout_s: float) -> float:
    if job_count < 0 or workers <= 0 or per_operation_timeout_s <= 0:
        raise ValueError("job_count must be non-negative and workers/timeout must be positive")
    lanes = min(workers, max(job_count, 1))
    waves = math.ceil(job_count / lanes)
    return 30.0 + (2.0 * per_operation_timeout_s * waves) + 10.0


def run(
    jobs: Iterable[Mapping[str, object]],
    *,
    sleigh_home: str,
    executable: str = "gnsdk-batch",
    timeout_s: float = 60,
    workers: int = 1,
) -> Iterator[dict[str, object]]:
    """Run the native JSONL batch executable and yield terminal result records."""
    if timeout_s <= 0 or workers <= 0:
        raise ValueError("timeout_s and workers must be positive")
    command = os.environ.get("GNSDK_BATCH_PATH", executable)
    with tempfile.TemporaryDirectory(prefix="gnsdk-batch-") as temp:
        input_path = os.path.join(temp, "jobs.jsonl")
        output_path = os.path.join(temp, "results.jsonl")
        job_count = 0
        with open(input_path, "w", encoding="utf-8") as stream:
            for job in jobs:
                stream.write(json.dumps(dict(job), sort_keys=True) + "\n")
                job_count += 1
        completed = subprocess.run(
            [command, "--sleigh-home", sleigh_home, "--input", input_path, "--output", output_path,
             "--timeout", str(max(1, int(timeout_s))), "--workers", str(workers)],
            text=True,
            capture_output=True,
            timeout=_process_timeout_s(job_count, workers, timeout_s),
            check=False,
        )
        if completed.returncode:
            raise RuntimeError(f"gnsdk-batch exited {completed.returncode}: {completed.stderr.strip()}")
        with open(output_path, encoding="utf-8") as stream:
            for line in stream:
                if line.strip():
                    yield json.loads(line)
