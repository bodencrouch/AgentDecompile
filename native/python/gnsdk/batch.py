"""JSONL subprocess client for gnsdk-batch; it intentionally needs no shared library."""

import json
import os
import subprocess
import tempfile
from typing import Iterable, Iterator, Mapping


def run(jobs: Iterable[Mapping[str, object]], *, sleigh_home: str, executable: str = "gnsdk-batch", timeout_s: float = 60) -> Iterator[dict[str, object]]:
    """Run the native JSONL batch executable and yield terminal result records."""
    command = os.environ.get("GNSDK_BATCH_PATH", executable)
    with tempfile.TemporaryDirectory(prefix="gnsdk-batch-") as temp:
        input_path = os.path.join(temp, "jobs.jsonl")
        output_path = os.path.join(temp, "results.jsonl")
        with open(input_path, "w", encoding="utf-8") as stream:
            for job in jobs:
                stream.write(json.dumps(dict(job), sort_keys=True) + "\n")
        completed = subprocess.run(
            [command, "--sleigh-home", sleigh_home, "--input", input_path, "--output", output_path,
             "--timeout", str(max(1, int(timeout_s)))],
            text=True, capture_output=True, timeout=timeout_s + 5, check=False,
        )
        if completed.returncode:
            raise RuntimeError(f"gnsdk-batch exited {completed.returncode}: {completed.stderr.strip()}")
        with open(output_path, encoding="utf-8") as stream:
            for line in stream:
                if line.strip():
                    yield json.loads(line)
