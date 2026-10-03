# Original external-provider canaries

These tiny fixtures are authored for AgentDecompile. They contain no original game
binary, recovered proprietary code, live Ghidra connection or model credentials.
The JSON snapshot is **synthetic**: its decompile and empty cross-reference lists
are known fixture inputs, not measured binary evidence. No assembly/CFG is invented.

`run_canaries.py` accepts an already installed isolated provider environment's bin
folder and a new scratch output directory. It copies fixtures, runs the real CLIs,
and retains exact argv/cwd, stdout/stderr, return codes and raw report digests.
The JSON arithmetic harnesses require `/usr/bin/python3` on this Linux host.

The benchmark has one matching case group and one deliberately incorrect candidate.
`expected_match: false` means ReAgent should detect that mismatch; the combined
benchmark exits zero when both expectations hold. It does **not** accept the wrong
candidate. The negative reccmp source deliberately repeats an annotation address
and should exit one with a duplicate-offset diagnostic. The snapshot plan should
retain the selected synthetic function and decompile text.

These checks establish provider CLI/report interoperability only. They do not
prove AgentDecompile's production adapter, binary parity, runtime equivalence,
source recovery, snapshot provenance or portability to another host/toolchain.
