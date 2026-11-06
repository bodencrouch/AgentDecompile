"""``python -m agentdecompile_recovery.native_snapshot`` entry point."""

from __future__ import annotations

import sys

from agentdecompile_recovery.native_snapshot.cli import main

if __name__ == "__main__":
    sys.exit(main())
