#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
export PYTHONDONTWRITEBYTECODE=1

status=0
failed=""
run_check() {
    name=$1
    shift
    if ! "$@"; then
        status=1
        failed="${failed}${failed:+, }${name}"
    fi
}

run_check "python tests" python3 -B -m unittest discover -s tests -p 'test_*.py' -v
run_check "markdownlint" npx --yes markdownlint-cli2@0.13.0 "*.md" "plugins/**/*.md" --config .markdownlint.yaml
run_check "git diff --check" git diff --check
if empty_tree=$(git hash-object -t tree /dev/null); then
    run_check "git diff --check (empty tree)" git diff --check "$empty_tree"
else
    status=1
    failed="${failed}${failed:+, }git diff --check (empty tree)"
fi

if [ "$status" -ne 0 ]; then
    printf 'failed checks: %s\n' "$failed" >&2
fi
exit "$status"
