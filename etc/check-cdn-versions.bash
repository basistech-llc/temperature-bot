#!/usr/bin/env bash
#
# Check CDN-loaded JavaScript/CSS libraries for newer versions.
# Called by `make outdated`.  Uses the npm registry as version source.
#
# Versions are defined in base.html as Jinja {% set %} variables.
# To update a version, change it there — all templates inherit it.
#
set -euo pipefail

BASE="${1:-app/templates/base.html}"

# Extract "{% set name = "value" %}" from base.html
get_version() {
    grep -o "{% set $1 = \"[^\"]*\" %}" "$BASE" | sed 's/.*= "//; s/" %}//'
}

# npm-package-name -> jinja variable name
declare -A LIBS=(
    [echarts]=echarts_version
    [tabulator-tables]=tabulator_version
    [purecss]=purecss_version
)

found=0
for pkg in "${!LIBS[@]}"; do
    var="${LIBS[$pkg]}"
    pinned=$(get_version "$var")
    if [ -z "$pinned" ]; then
        printf "%-25s %-10s (not found in %s)\n" "$pkg" "???" "$BASE"
        found=1
        continue
    fi

    latest=$(npm view "$pkg" version 2>/dev/null || echo "???")

    if [ "$pinned" != "$latest" ]; then
        printf "%-25s %-10s %-10s\n" "$pkg" "$pinned" "$latest"
    fi
done
