from collections import defaultdict

from docstub import _utils


class Test_module_name_from_path:
    def test_basic(self, tmp_path):
        # Package structure
        structure = [
            "foo/",
            "foo/__init__.py",
            "foo/bar.py",
            "foo/baz/",
            "foo/baz/__init__.py",
            "foo/baz/qux.py",
        ]
        for item in structure:
            path = tmp_path / item
            if item.endswith(".py"):
                path.touch()
            else:
                path.mkdir()

        assert _utils.module_name_from_path(tmp_path / "foo/__init__.py") == "foo"
        assert _utils.module_name_from_path(tmp_path / "foo/bar.py") == "foo.bar"
        assert (
            _utils.module_name_from_path(tmp_path / "foo/baz/__init__.py") == "foo.baz"
        )
        assert (
            _utils.module_name_from_path(tmp_path / "foo/baz/qux.py") == "foo.baz.qux"
        )


def test_pyfile_checksum(tmp_path):
    # Create package
    package_dir = tmp_path / "mypackage"
    package_dir.mkdir()
    package_init = package_dir / "__init__.py"
    package_init.touch()

    # Create submodule to be checked
    submodule_name = "submodule.py"
    submodule_path = package_dir / submodule_name
    with submodule_path.open("w") as fp:
        fp.write("# First line\n")

    original_key = _utils.pyfile_checksum(submodule_path)
    # Check that the key is stable
    assert original_key == _utils.pyfile_checksum(submodule_path)

    # Key changes if content changes
    with submodule_path.open("a") as fp:
        fp.write("# Second line\n")
    changed_content_key = _utils.pyfile_checksum(submodule_path)
    assert original_key != changed_content_key

    # Key changes if qualname / path of module changes
    new_package_dir = package_dir.rename(tmp_path / "newpackage")
    qualname_changed_key = _utils.pyfile_checksum(new_package_dir / submodule_name)
    assert qualname_changed_key != changed_content_key


def test_create_cachedir(tmp_path):
    cache_dir = tmp_path / ".test_cache_dir"
    assert not cache_dir.exists()

    _utils.create_cachedir(cache_dir)
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
    _utils.create_cachedir(cache_dir)


class Test_FileCache:
    def test_basic(self, tmp_path):

        class Serializer:
            suffix = ".txt"

            def hash_args(self, arg):
                return str(hash(arg))

            def serialize(self, data):
                return str(data).encode()

            def deserialize(self, raw):
                return int(raw.decode())

        counter = defaultdict(lambda: 0)

        def square(x):
            counter[x] += 1
            return x * x

        cached_square = _utils.FileCache(
            func=square, serializer=Serializer(), cache_dir=tmp_path, name="test"
        )

        assert cached_square(3) == 9
        assert counter[3] == 1

        # Result was cached
        entry_name = f"{Serializer().hash_args(3)!s}{Serializer.suffix}"
        cached_file = tmp_path / "test" / entry_name
        assert cached_file.is_file()

        # With the square(3) cached, the counter no longer increases
        assert cached_square(3) == 9
        assert counter[3] == 1

        # Using another FileCache will use the existing cache
        cached_square_2 = _utils.FileCache(
            func=square, serializer=Serializer(), cache_dir=tmp_path, name="test"
        )
        assert cached_square_2(3) == 9
        assert counter[3] == 1

        # But using another FileCache with a different name will not hit existing cache
        cached_square_3 = _utils.FileCache(
            func=square,
            serializer=Serializer(),
            cache_dir=tmp_path,
            name="test2",
        )
        assert cached_square_3(3) == 9
        assert counter[3] == 2
