#!/bin/bash
# Blobless bare clone of one BAITC-Hacks repo into $WORK/clones (history + trees, no file contents).
# usage: jq -r .name work/all_repos.jsonl | xargs -P 24 -n 1 pipeline/clone_one.sh
WORK="${WORK:-$(cd "$(dirname "$0")/.." && pwd)/work}"
name="$1"
dir="$WORK/clones/$name"
mkdir -p "$WORK/clones"
if [ -f "$dir/HEAD" ]; then exit 0; fi
GIT_TERMINAL_PROMPT=0 timeout 300 git clone -q --bare --filter=blob:none "https://github.com/BAITC-Hacks/$name.git" "$dir" 2>"$dir.err" && rm -f "$dir.err"
