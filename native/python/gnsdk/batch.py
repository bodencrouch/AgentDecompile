"""JSONL subprocess client for gnsdk-batch; it intentionally needs no shared library."""

import json
import os
import subprocess
from typing import Iterable, Iterator, Mapping


def run(jobs: Iterable[Mapping[str, object]], *, executable: str = "gnsdk-batch", timeout_s: float = 60) -> Iterator[dict[str, object]]:
    """Run the native JSONL batch executable and yield terminal result records."""
    command = os.environ.get("GNSDK_BATCH_PATH", executable)
    payload = "".join(json.dumps(dict(job), sort_keys=True) + "\n" for job in jobs)
    completed = subprocess.run([command], input=payload, text=True, capture_output=True, timeout=timeout_s, check=False)
    if completed.returncode:
        raise RuntimeError(f"gnsdk-batch exited {completed.returncode}: {completed.stderr.strip()}")
    for line in completed.stdout.splitlines():
        yield json.loads(line)
