#!/usr/bin/env bash
# publish.sh — validate sidebar links, then commit and push the wiki.
# Usage: ./publish.sh ["commit message"]

cd "$(dirname "$0")" || exit 1

echo "== Validating _sidebar.md links =="
missing=0
while IFS= read -r link; do
  file=".${link}"   # sidebar links are root-relative, e.g. /GPU-Systems/GEMM.md
  if [ ! -f "$file" ]; then
    echo "  BROKEN: $link"
    missing=$((missing + 1))
  fi
done < <(grep -oE '\]\(/[^)]+\)' _sidebar.md | sed 's/](\(.*\))/\1/')

total=$(grep -cE '\]\(/[^)]+\)' _sidebar.md)
echo "  $((total - missing))/$total links OK"

if [ "$missing" -gt 0 ]; then
  echo "ERROR: $missing broken sidebar link(s). Fix before publishing."
  exit 1
fi

if [ -z "$(git status -s)" ]; then
  echo "== No changes to publish =="
  exit 0
fi

msg="${1:-Wiki update $(date '+%Y-%m-%d %H:%M')}"

echo "== Committing =="
git add -A
git commit -m "$msg" || exit 1

echo "== Pushing =="
git push || exit 1

echo "== Published: $msg =="
