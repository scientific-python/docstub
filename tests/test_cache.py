from collections import defaultdict
from pathlib import Path

import pytest

from docstub import _cache


def test_directory_size():
    assert _cache._directory_size(Path(__file__).parent) > 0
    with pytest.raises(FileNotFoundError, match=r"doesn't exist, can't determine size"):
        _cache._directory_size(Path("i/don't/exist"))


def test_create_cache(tmp_path):
    cache_dir = tmp_path / ".test_cache_dir"
    assert not cache_dir.exists()

    _cache.create_cache(cache_dir)
    assert cache_dir.is_dir()

    # Check CACHEDIR.TAG file
    cache_tag_path = cache_dir / "CACHEDIR.TAG"
    assert cache_tag_path.is_file()
    with cache_tag_path.open("r") as fp:
        cache_tag_content = fp.read()
    assert cache_tag_content.startswith("Signature: 8a477f597d28d172789f06886806bc55\n")

    # Check. gitignore
    gitignore_path = cache_dir / ".gitignore"
    assert gitignore_path.is_file()
    with gitignore_path.open("r") as fp:
        gitignore_content = fp.read()
    assert "\n*\n" in gitignore_content

    # Check that calling it a second time doesn't raise an error
    _cache.create_cache(cache_dir)


def test_create_validate_cache(tmp_path):
    cache_dir = tmp_path / _cache.CACHE_DIR_NAME
    _cache.create_cache(cache_dir)
    _cache.validate_cache(cache_dir)

    with pytest.raises(FileNotFoundError, match=r"expected directory .* named .*"):
        _cache.validate_cache(tmp_path)


class Test_FileCache:
    def test_basic(self, tmp_path):
        class Serializer:
            suffix = ".txt"

            def hash_args(self, arg: int) -> str:
                return str(hash(arg))

            def serialize(self, data: int) -> bytes:
                return str(data).encode()

            def deserialize(self, raw: bytes) -> int:
                return int(raw.decode())

        counter = defaultdict(lambda: 0)

        def square(x):
            counter[x] += 1
            return x * x

        cached_square = _cache.FileCache(
            func=square, serializer=Serializer(), cache_dir=tmp_path, sub_dir="test"
        )
        assert cached_square.cached_last_call is None

        assert cached_square(3) == 9
        assert counter[3] == 1
        assert cached_square.cache_misses == 1
        assert cached_square.cache_hits == 0
        assert cached_square.cached_last_call is False

        # Result was cached
        entry_name = f"{Serializer().hash_args(3)!s}{Serializer.suffix}"
        cached_file = tmp_path / "test" / entry_name
        assert cached_file.is_file()

        # With the square(3) cached, the counter no longer increases
        assert cached_square(3) == 9
        assert counter[3] == 1
        assert cached_square.cache_misses == 1
        assert cached_square.cache_hits == 1
        assert cached_square.cached_last_call is True

        # Using another FileCache will use the existing cache
        cached_square_2 = _cache.FileCache(
            func=square, serializer=Serializer(), cache_dir=tmp_path, sub_dir="test"
        )
        assert cached_square_2(3) == 9
        assert counter[3] == 1
        assert cached_square_2.cache_misses == 0
        assert cached_square_2.cache_hits == 1
        assert cached_square_2.cached_last_call is True

        # But using another FileCache with a different name will not hit existing cache
        cached_square_3 = _cache.FileCache(
            func=square,
            serializer=Serializer(),
            cache_dir=tmp_path,
            sub_dir="test2",
        )
        assert cached_square_3(3) == 9
        assert counter[3] == 2
        assert cached_square_3.cache_misses == 1
        assert cached_square_3.cache_hits == 0
        assert cached_square_3.cached_last_call is False
