#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MG5="${MG5:-$ROOT/MG5_aMC_v3_8_1}"
PYTHON="${PYTHON:-python3}"

if [ ! -x "$MG5/bin/mg5_aMC" ]; then
    echo "MG5aMC not found at $MG5; set MG5=/path/to/MG5_aMC" >&2
    exit 1
fi

bash "$ROOT/install.sh" --mg5 "$MG5" --from-local

TMPDIR="$(mktemp -d)"
trap 'rm -rf "$TMPDIR"' EXIT

cat > "$TMPDIR/proc_card" <<'EOF'
import model loop_sm
generate p p > t t~ [QCD]
display diagrams OUT --no_open --merge
display diagrams_text OUT --no_open --merge
quit
EOF
sed -i "s|OUT|$TMPDIR/out|" "$TMPDIR/proc_card"

cd "$TMPDIR"
"$MG5/bin/mg5_aMC" --mode=nlo_diagram_displays "$TMPDIR/proc_card" > mg5.log 2>&1

test -f "$TMPDIR/out/all_diagrams.pdf"
test -f "$TMPDIR/out/all_diagrams_text.txt"
[ "$(head -c 4 "$TMPDIR/out/all_diagrams.pdf")" = '%PDF' ]

echo "smoke OK: $(ls "$TMPDIR/out" | wc -l) files in $TMPDIR/out"
