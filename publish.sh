#!/usr/bin/env bash
# Publish the public profile branch from the generator branch.
#
#   main     = what github.com shows: README.md + assets/*.svg (+ .gitignore)
#   tooling  = everything else: build.py, verify.py, repos.json, preview.html, ...
#
# The working tree stays on `tooling`; this script builds main's tree through a
# temporary index so no file is ever checked out or deleted on disk.
#
#   ./publish.sh                 # rebuild, verify, publish "update cards"
#   ./publish.sh "new repo row"  # publish with a message
set -euo pipefail
cd "$(dirname "$0")"

PUB=main
SRC=$(git rev-parse --abbrev-ref HEAD)
PY=.venv/bin/python
IDX=.git/publish-index
MSG=${1:-update cards}

[ -x "$PY" ] || PY=python3

echo "== build + verify on $SRC"
"$PY" build.py
"$PY" verify.py

echo "== assemble $PUB"
rm -f "$IDX"
GIT_INDEX_FILE=$IDX git read-tree "$SRC"
GIT_INDEX_FILE=$IDX git ls-files -z | while IFS= read -r -d '' f; do
  case "$f" in
    README.md|.gitignore|assets/*) : ;;              # published
    *) GIT_INDEX_FILE=$IDX git rm --cached -q -- "$f" ;;
  esac
done
TREE=$(GIT_INDEX_FILE=$IDX git write-tree)
rm -f "$IDX"

PARENT=()
git rev-parse --verify --quiet "refs/heads/$PUB" >/dev/null && PARENT=(-p "refs/heads/$PUB")
COMMIT=$(git commit-tree "$TREE" "${PARENT[@]}" -m "profile: $MSG")
git branch -f "$PUB" "$COMMIT"

echo "== $PUB tree"
git ls-tree -r --name-only "$PUB"

if git ls-remote --exit-code --heads origin "$PUB" >/dev/null 2>&1; then
  git push origin "$PUB" --force-with-lease
else
  git push -u origin "$PUB"
fi
echo "== done: $(git rev-parse --short "$PUB")"
