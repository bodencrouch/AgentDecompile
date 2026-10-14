"""Recover on-disk FileBytes from a Ghidra program. Destination is required."""

from __future__ import annotations

from pathlib import Path
import hashlib
import re
import tempfile


CHUNK = 1 << 20


def export(program, dest: Path, *, overwrite: bool = False) -> list[dict]:
    """Write every original blob, no-clobber unless legacy overwrite is explicit."""
    import jpype

    dest = Path(dest)
    mem = program.getMemory()
    all_fb = list(mem.getAllFileBytes())
    if not all_fb:
        raise ValueError("Program has no original FileBytes; memory export cannot recover the original file layout.")
    meta = []
    for idx, fb in enumerate(all_fb):
        size = int(fb.getSize())
        name = str(fb.getFilename())
        safe = re.sub(r"[^A-Za-z0-9._-]", "_", name)
        out = dest if len(all_fb) == 1 else dest.with_name(f"{dest.name}.{idx}_{safe}")
        out.parent.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha256()
        created = False
        staging = out
        try:
            if overwrite:
                # Preserve the previous complete blob if replacement fails.
                fh = tempfile.NamedTemporaryFile(mode="wb", dir=out.parent, prefix=f".{out.name}.", delete=False)
                staging = Path(fh.name)
            else:
                fh = open(out, "xb")
            created = True
            with fh:
                off = 0
                jbuf = jpype.JArray(jpype.JByte)(CHUNK)
                while off < size:
                    n = min(CHUNK, size - off)
                    got = int(fb.getOriginalBytes(off, jbuf, 0, n))
                    if got <= 0 or got > n:
                        raise OSError(f"Incomplete FileBytes at offset {off} of {size}")
                    chunk = bytes(memoryview(jbuf).cast("B")[:got])
                    fh.write(chunk)
                    digest.update(chunk)
                    off += got
            if overwrite:
                staging.replace(out)
        except BaseException as exc:
            # The context has closed the file, including on flush/close failure.
            # Never delete an existing destination when exclusive open failed.
            if created:
                try:
                    staging.unlink(missing_ok=True)
                except OSError as cleanup_error:
                    add_note = getattr(exc, "add_note", None)
                    if callable(add_note):
                        add_note(f"Incomplete output cleanup failed for {staging}: {cleanup_error}")
            raise
        meta.append(
            {
                "index": idx,
                "filename": name,
                "size": size,
                "written": out.stat().st_size,
                "out": str(out),
                "sha256": digest.hexdigest(),
                "file_offset": int(fb.getFileOffset()),
                "source": "ghidra-original-filebytes",
                "whole_original_file_verified": False,
            }
        )
    return meta
