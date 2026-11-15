# madgraph_nlo_diagram_displays

A MadGraph5_aMC@NLO plugin that enables the output options of PR [#398](https://github.com/mg5amcnlo/mg5amcnlo/pull/398) for **NLO** diagram displays.

PR #398 added `--no_open`, an output directory and `--merge` to `display diagrams` and `display diagrams_text` for LO processes (merged into MG5aMC 3.8.0). The aMC@NLO interface still rejects these options for NLO processes. This plugin adds them for NLO without modifying any MG5 source file; the corresponding upstream change is [PR #482](https://github.com/mg5amcnlo/mg5amcnlo/pull/482).

Requires **MG5aMC >= 3.8.0** (the release that contains PR #398). Older releases have no `--no_open`/`--merge` parsers and are rejected at load time.

## Install

```bash
./install.sh --mg5 /path/to/MG5_aMC_v3_8_1
```

Or, from a local clone:

```bash
./install.sh --mg5 /path/to/MG5_aMC_v3_8_1 --from-local
```

`install.sh` copies the plugin into `MG5_aMC/PLUGIN/nlo_diagram_displays` and creates `bin/mg5_aMC_nlo_diagram_displays`.

## Run

```bash
/path/to/MG5_aMC_v3_8_1/bin/mg5_aMC --mode=nlo_diagram_displays
```

or:

```bash
/path/to/MG5_aMC_v3_8_1/bin/mg5_aMC_nlo_diagram_displays
```

All normal MG5 commands remain available in this shell, including the LO/NLO interface switching.

## Usage

```text
generate p p > t t~ [QCD]
display diagrams ./diagrams/ttbarQCD --no_open --merge
display diagrams_text ./diagrams/ttbarQCD --no_open --merge
```

- `display diagrams [born|real|virt|loop] DIR --no_open --merge` writes one `.eps` per amplitude (prefixed with the diagram type so born and loop files do not overwrite each other), then merges them into `DIR/all_diagrams.pdf` with Ghostscript. `--merge` requires an explicit directory.
- `display diagrams_text [born|real|virt|loop] DIR --no_open --merge` writes one `.txt` per amplitude (prefixed with the diagram type) and merges them into `DIR/all_diagrams_text.txt`. Both flags require an explicit directory.
- Without a selector, all three NLO diagram types (born, real, loop) are written and merged once.
- Requesting a type with no amplitudes prints `No "<type>" diagrams exist for this process. Skipping ...` instead of raising.
- `virt` is an alias for `loop`.
- Single-dash `-no_open` / `-merge` are accepted, as in LO.
- Merged outputs are written to a temporary file and `os.replace`d, so a failed merge never truncates an existing `all_diagrams.pdf` / `all_diagrams_text.txt`.

LO and loop-induced displays are untouched: they keep the stock MG5aMC behaviour.

## Note: loop-induced decay chains (local MG5 fix)

Stock MG5 3.8.1 crashes in `display diagrams` for e.g. `g g > h > l- l+ l- l+ [noborn=QCD]`: empty `structure_repository` but tagged diagrams → `IndexError` in `LoopFeynmanDiagram` (`madgraph/core/drawing.py`). Upstream bug, also in plain `mg5_aMC`. Local fix in `madgraph/core/drawing.py`:

```diff
- if self.diagram['tag'] and not self.fdstructures is None:   # load_diagram
+ if self.diagram['tag'] and self.fdstructures:
- if not self.fdstructures is None:                           # need_to_flip
+ if self.fdstructures:
```

Skip the optional structure pre-loading when empty; the parent builds the real diagram. `display diagrams ... --merge` then works in MadLoop too.

## Test

Install the plugin first, then run the full suite:

```bash
PYTHONPATH="$PWD:$PWD/MG5_aMC_v3_8_1" \
  python -m unittest discover -s tests -p 'test_*.py' -v
```

For a quick installation/PDF check:

```bash
./tests/smoke.sh
```

Set `MG5` and `PYTHON` when needed:

```bash
MG5=/path/to/MG5_aMC_v3_8_1 PYTHON=~/miniconda3/envs/py310/bin/python ./tests/smoke.sh
```

GitHub Actions runs the suite against MG5aMC 3.8.0 and 3.8.1.

## Scope

- Only `display diagrams` and `display diagrams_text` at NLO are changed.
- Ghostscript (`gs`) must be on `PATH` for `--merge` to produce a PDF.
