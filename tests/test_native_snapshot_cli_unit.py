from agentdecompile_recovery.native_snapshot.cli import build_parser


def test_diff_subcommand_requires_native_inputs():
    parser = build_parser()
    args = parser.parse_args(["diff", "snapshot", "--console", "console", "--sleigh-home", "sleigh"])
    assert args.command == "diff"
    assert args.mode == "console"
    assert args.timeout_s == 60
    assert args.output is None


def test_replay_subcommand_accepts_batch_backend():
    parser = build_parser()
    args = parser.parse_args([
        "replay",
        "snapshot",
        "--mode",
        "batch",
        "--batch",
        "gnsdk-batch",
        "--sleigh-home",
        "sleigh",
        "--workers",
        "2",
        "--tmpdir",
        "tmp",
    ])
    assert args.command == "replay"
    assert args.mode == "batch"
    assert args.workers == 2
    assert args.per_process == 200
    assert str(args.tmpdir) == "tmp"
