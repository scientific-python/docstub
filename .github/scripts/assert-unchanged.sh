#!/usr/bin/env bash

# Assert that there are no changes in a given directory compared to HEAD.
# Expects a relative directory as the one and only argument.

set -e

CHECK_DIR=$1

# Find untracked files
UNTRACKED=$(git ls-files --others --exclude-standard "$CHECK_DIR")
# and display their content by comparing with '/dev/null'
echo "$UNTRACKED" | xargs -I _ git --no-pager diff --no-index /dev/null _

# Display changes in tracked files and capture non-zero exit code if so
set +e
git diff --exit-code HEAD "$CHECK_DIR"
GIT_DIFF_HEAD_EXIT_CODE=$?
set -e

# Display changes in tracked files and capture exit status
if [ $GIT_DIFF_HEAD_EXIT_CODE -ne 0 ] ||  [ -n "$UNTRACKED" ]; then
  echo "::error::Uncommited changes in directory '$CHECK_DIR'"
  exit 1
else
  echo "::notice::No Uncommited changes, directory '$CHECK_DIR' is clean"
fi

set +e
