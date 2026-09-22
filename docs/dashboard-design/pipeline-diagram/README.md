# Recovery pipeline diagram (local, editable)

One picture of everything the recovery pipeline is designed to do: the eight ordered
stages, the five lanes that run concurrently beside them (identity fusion, cross-build export, runtime reuse, verification, distributed compute), the exhaustive resolution
ladders, the serialization locks, the export bundle, and the legend.

| File | What it is |
|---|---|
| `agentdecompile-recovery-pipeline.drawio` | The editable diagram. Open with draw.io desktop (`drawio <file>`), the VS Code "Draw.io Integration" extension, or app.diagrams.net. One layer per row, one group per card. |
| `agentdecompile-recovery-pipeline.svg` | The same diagram as plain SVG; opens and edits in Inkscape or any browser. |
| `agentdecompile-recovery-pipeline.png` | A rendered copy for quick viewing. |
| `generate_pipeline_diagram.py` | Source of truth. Edit the text and layout here, then run it to regenerate the SVG. |
| `svg_to_drawio.py` | Turns the generated SVG into the `.drawio` file (native cells, layers, groups, connectors). |

Regenerate everything:

```bash
python generate_pipeline_diagram.py
python svg_to_drawio.py agentdecompile-recovery-pipeline.svg agentdecompile-recovery-pipeline.drawio
xvfb-run -a drawio --no-sandbox -x -f png -o agentdecompile-recovery-pipeline.png agentdecompile-recovery-pipeline.drawio
```

Both scripts are deterministic: the same source produces byte-identical output.
