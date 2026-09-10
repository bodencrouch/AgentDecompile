from pathlib import Path

from agentdecompile_recovery.native_snapshot.cli import build_parser


def test_diff_subcommand_requires_native_inputs():
    parser = build_parser()
    args = parser.parse_args(["diff", "snapshot", "--console", "console", "--sleigh-home", "sleigh"])
    assert args.command == "diff"
    assert args.timeout_s == 60
    assert args.output is None
