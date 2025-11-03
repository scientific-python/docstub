# Copyright: 2001-2025, Python Software Foundation
# License: PSF-2.0
#
# See LICENSE.txt for the full license text

"""Vendored snippets from Python's standard library.

These are not available yet in all supported Python versions.
"""

import os
import re
from collections.abc import Sequence
from concurrent.futures import ProcessPoolExecutor as _ProcessPoolExecutor


# Vendored `fnmatch._translate` from Python 3.13.4 because it isn't available in
# earlier Python versions and needed for `glob_translate` below. Copied from
# https://github.com/python/cpython/blob/8a526ec7cbea8fafc9dae4b3dd6371906b9be342/Lib/fnmatch.py#L85-L154
def _fnmatch_translate(pat: str, STAR: str, QUESTION_MARK: str) -> str:
    res = []
    add = res.append
    i, n = 0, len(pat)
    while i < n:
        c = pat[i]
        i = i + 1
        if c == "*":
            # compress consecutive `*` into one
            if (not res) or res[-1] is not STAR:
                add(STAR)
        elif c == "?":
            add(QUESTION_MARK)
        elif c == "[":
            j = i
            if j < n and pat[j] == "!":
                j = j + 1
            if j < n and pat[j] == "]":
                j = j + 1
            while j < n and pat[j] != "]":
                j = j + 1
            if j >= n:
                add("\\[")
            else:
                stuff = pat[i:j]
                if "-" not in stuff:
                    stuff = stuff.replace("\\", r"\\")
                else:
                    chunks = []
                    k = i + 2 if pat[i] == "!" else i + 1
                    while True:
                        k = pat.find("-", k, j)
                        if k < 0:
                            break
                        chunks.append(pat[i:k])
                        i = k + 1
                        k = k + 3
                    chunk = pat[i:j]
                    if chunk:
                        chunks.append(chunk)
                    else:
                        chunks[-1] += "-"
                    # Remove empty ranges -- invalid in RE.
                    for k in range(len(chunks) - 1, 0, -1):
                        if chunks[k - 1][-1] > chunks[k][0]:
                            chunks[k - 1] = chunks[k - 1][:-1] + chunks[k][1:]
                            del chunks[k]
                    # Escape backslashes and hyphens for set difference (--).
                    # Hyphens that create ranges shouldn't be escaped.
                    stuff = "-".join(
                        s.replace("\\", r"\\").replace("-", r"\-") for s in chunks
                    )
                # Escape set operations (&&, ~~ and ||).
                stuff = re.sub(r"([&~|])", r"\\\1", stuff)
                i = j + 1
                if not stuff:
                    # Empty range: never match.
                    add("(?!)")
                elif stuff == "!":
                    # Negated empty range: match any character.
                    add(".")
                else:
                    if stuff[0] == "!":
                        stuff = "^" + stuff[1:]
                    elif stuff[0] in ("^", "["):
                        stuff = "\\" + stuff
                    add(f"[{stuff}]")
        else:
            add(re.escape(c))
    assert i == n
    return res


# Vendored `glob.translate` from Python 3.13.4 because it isn't available in
# earlier Python versions. Copied from
# https://github.com/python/cpython/blob/8a526ec7cbea8fafc9dae4b3dd6371906b9be342/Lib/glob.py#L267-L319
def glob_translate(
    pat: str,
    *,
    recursive: bool = False,
    include_hidden: bool = False,
    seps: Sequence[str] | None = None,
) -> str:
    """Translate a pathname with shell wildcards to a regular expression.

    If `recursive` is true, the pattern segment '**' will match any number of
    path segments.

    If `include_hidden` is true, wildcards can match path segments beginning
    with a dot ('.').

    If a sequence of separator characters is given to `seps`, they will be
    used to split the pattern into segments and match path separators. If not
    given, os.path.sep and os.path.altsep (where available) are used.
    """
    if not seps:
        if os.path.altsep:
            seps = (os.path.sep, os.path.altsep)
        else:
            seps = os.path.sep
    escaped_seps = "".join(map(re.escape, seps))
    any_sep = f"[{escaped_seps}]" if len(seps) > 1 else escaped_seps
    not_sep = f"[^{escaped_seps}]"
    if include_hidden:
        one_last_segment = f"{not_sep}+"
        one_segment = f"{one_last_segment}{any_sep}"
        any_segments = f"(?:.+{any_sep})?"
        any_last_segments = ".*"
    else:
        one_last_segment = f"[^{escaped_seps}.]{not_sep}*"
        one_segment = f"{one_last_segment}{any_sep}"
        any_segments = f"(?:{one_segment})*"
        any_last_segments = f"{any_segments}(?:{one_last_segment})?"

    results = []
    parts = re.split(any_sep, pat)
    last_part_idx = len(parts) - 1
    for idx, part in enumerate(parts):
        if part == "*":
            results.append(one_segment if idx < last_part_idx else one_last_segment)
        elif recursive and part == "**":
            if idx < last_part_idx:
                if parts[idx + 1] != "**":
                    results.append(any_segments)
            else:
                results.append(any_last_segments)
        else:
            if part:
                if not include_hidden and part[0] in "*?":
                    results.append(r"(?!\.)")
                results.extend(_fnmatch_translate(part, f"{not_sep}*", not_sep))
            if idx < last_part_idx:
                results.append(any_sep)
    res = "".join(results)
    return rf"(?s:{res})\Z"


# Vendored `ProcessPoolExecutor.terminate_workers` from Python 3.14 because
# it isn't available in earlier Python versions. Copied from
# https://github.com/python/cpython/blob/02604314ba3e97cc1918520e9ef5c0c4a6e7fe47/Lib/concurrent/futures/process.py#L878-L939
if not hasattr(_ProcessPoolExecutor, "terminate_workers"):
    _TERMINATE: str = "terminate"
    _KILL: str = "kill"

    _SHUTDOWN_CALLBACK_OPERATION: set[str] = {_TERMINATE, _KILL}

    class ProcessPoolExecutor(_ProcessPoolExecutor):
        def _force_shutdown(self, operation: str) -> None:
            """Attempts to terminate or kill the executor's workers based off the
            given operation. Iterates through all of the current processes and
            performs the relevant task if the process is still alive.

            After terminating workers, the pool will be in a broken state
            and no longer usable (for instance, new tasks should not be
            submitted).
            """
            if operation not in _SHUTDOWN_CALLBACK_OPERATION:
                raise ValueError(f"Unsupported operation: {operation!r}")

            processes = {}
            if self._processes:
                processes = self._processes.copy()

            # shutdown will invalidate ._processes, so we copy it right before
            # calling. If we waited here, we would deadlock if a process decides not
            # to exit.
            self.shutdown(wait=False, cancel_futures=True)

            if not processes:
                return

            for proc in processes.values():
                try:
                    if not proc.is_alive():
                        continue
                except ValueError:
                    # The process is already exited/closed out.
                    continue

                try:
                    if operation == _TERMINATE:
                        proc.terminate()
                    elif operation == _KILL:
                        proc.kill()
                except ProcessLookupError:
                    # The process just ended before our signal
                    continue

        def terminate_workers(self) -> None:
            """Attempts to terminate the executor's workers.
            Iterates through all of the current worker processes and terminates
            each one that is still alive.

            After terminating workers, the pool will be in a broken state
            and no longer usable (for instance, new tasks should not be
            submitted).
            """
            return self._force_shutdown(operation=_TERMINATE)

        def kill_workers(self) -> None:
            """Attempts to kill the executor's workers.
            Iterates through all of the current worker processes and kills
            each one that is still alive.

            After killing workers, the pool will be in a broken state
            and no longer usable (for instance, new tasks should not be
            submitted).
            """
            return self._force_shutdown(operation=_KILL)

else:
    ProcessPoolExecutor: _ProcessPoolExecutor = _ProcessPoolExecutor  # type: ignore[no-redef]
