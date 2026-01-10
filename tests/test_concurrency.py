import math
import os

import pytest

from docstub._concurrency import guess_concurrency_params


class Test_guess_concurrency_params:
    @pytest.mark.parametrize("task_count", list(range(9)))
    @pytest.mark.parametrize("cpu_count", [1, 8])
    def test_default_below_cutoff(self, task_count, cpu_count, monkeypatch):
        monkeypatch.setattr(os, "cpu_count", lambda: cpu_count)
        monkeypatch.setattr(os, "process_cpu_count", lambda: cpu_count, raising=False)
        worker_count, chunk_size = guess_concurrency_params(task_count=task_count)
        assert worker_count == 1
        assert chunk_size == task_count

    @pytest.mark.parametrize("task_count", [10, 15, 50, 100, 1000])
    @pytest.mark.parametrize("cpu_count", [1, 8, 16])
    def test_default(self, task_count, cpu_count, monkeypatch):
        monkeypatch.setattr(os, "cpu_count", lambda: cpu_count)
        monkeypatch.setattr(os, "process_cpu_count", lambda: cpu_count, raising=False)
        worker_count, chunk_size = guess_concurrency_params(task_count=task_count)
        assert worker_count == min(cpu_count, task_count // 3)
        assert chunk_size == math.ceil(task_count / worker_count)
