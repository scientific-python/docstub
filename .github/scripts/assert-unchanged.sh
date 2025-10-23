#!/usr/bin/env bash

# Assert that there are no changes in a given directory compared to HEAD.
# Expects a relative directory as the one and only argument.

set -e

CHECK_DIR=$1

# Add untracked files so the following command picks them up
UNTRACKED=$(git ls-files --others --exclude-standard "$CHECK_DIR")

if [ -n "$UNTRACKED" ]; then
  git add "$UNTRACKED"
fi

set +e
# Display changes in tracked files and capture non-zero exit code if so
git diff --exit-code HEAD "$CHECK_DIR"
GIT_DIFF_EXIT_CODE=$?
set -e

# Unstage again (useful for local debugging)
if [ -n "$UNTRACKED" ]; then
   git restore --staged "$UNTRACKED"
fi

# Display changes in tracked files and capture exit status
if [ $GIT_DIFF_EXIT_CODE -ne 0 ]; then
  echo "::error::Uncommited changes in directory: $CHECK_DIR"
  exit $GIT_DIFF_EXIT_CODE
fi

set +e