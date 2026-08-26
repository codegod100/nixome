#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root"

graph_result="$(buck2 build //:gnomeos-graph-lock --show-output |
  awk '$1 == "root//:gnomeos-graph-lock" { print $2 }')"
source_result="$(buck2 build //:gnomeos-source-lock --show-output |
  awk '$1 == "root//:gnomeos-source-lock" { print $2 }')"

if [[ -z "$graph_result" || -z "$source_result" ]]; then
  echo "failed to locate generated GNOME OS locks" >&2
  exit 1
fi

python -m bst2nix.cli generate-buck-sources \
  "$source_result/source-lock.json" \
  -o generated/sources/BUCK
python -m bst2nix.cli generate-buck-elements \
  "$graph_result/graph-lock.json" \
  "$source_result/source-lock.json" \
  -o generated/elements/BUCK

echo "Generated native GNOME OS cells."
echo "Build with: buck2 build //:gnomeos-oci --show-output"
