"""Implementation of ``docstub run``.

Its interface declaration is in ``_cli.py``. Splitting declaration and
implementation (with slow imports) speeds up the ``--help`` option.
"""

import importlib.util
import logging
import sys
import time
from collections import Counter
from contextlib import contextmanager
from pathlib import Path

import pluggy

from . import doctype, plugins
from ._analysis import (
    PyImport,
    TypeCollector,
    TypeMatcher,
    common_known_types,
)
from ._cache import CACHE_DIR_NAME, FileCache
from ._concurrency import LoggingProcessExecutor, guess_concurrency_params
from ._config import Config
from ._path_utils import (
    STUB_HEADER_COMMENT,
    find_package_root,
    walk_source_and_targets,
    walk_source_package,
)
from ._report import Stats, setup_logging
from ._stubs import Py2StubTransformer, try_format_stub
from ._utils import escape_qualname
from ._version import __version__

logger: logging.Logger = logging.getLogger(__name__)


def cache_dir_in_cwd():
    """Return cache directory for and in current working directory.

    Returns
    -------
    cache_dir : Path
    """
    return Path.cwd() / CACHE_DIR_NAME


def _load_configuration(config_paths=None):
    """Load and merge configuration from CWD and optional files.

    Parameters
    ----------
    config_paths : list[Path]

    Returns
    -------
    config : ~.Config
    """
    config = Config.from_toml(Config.TEMPLATE_PATH)
    numpy_config = Config.from_toml(Config.NUMPY_PATH)
    config = config.merge(numpy_config)

    if config_paths:
        for path in config_paths:
            add_config = Config.from_toml(path)
            logger.info("Using %s", path)
            config = config.merge(add_config)

    else:
        pyproject_toml = Path.cwd() / "pyproject.toml"
        if pyproject_toml.is_file():
            logger.info("Using %s", pyproject_toml)
            add_config = Config.from_toml(pyproject_toml)
            config = config.merge(add_config)

        docstub_toml = Path.cwd() / "docstub.toml"
        if docstub_toml.is_file():
            add_config = Config.from_toml(docstub_toml)
            logger.info("Using %s", docstub_toml)
            config = config.merge(add_config)

    return config


def _import_standalone_module_from_path(path, *, module_name=None):
    """Import standalone module at the given file path.

    "Standalone" because relative imports inside the loaded module may not work?

    Parameters
    ----------
    path : Path
        Path to a Python file.
    module_name : str, optional
        The name to load the module as. Derived from `path` if not provided.
        The functions raises if such a module already exists in :mod:`sys.modules`.

    Returns
    -------
    module : ModuleType
    """
    module_name = module_name or escape_qualname(str(path))
    if module_name in sys.modules:
        raise RuntimeError(f"module {module_name} already defined")

    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _load_plugins(paths=()):
    """Load plugins for docstub.

    Parameters
    ----------
    paths : Iterable of Path(s)
        File paths to load plugins from.

    Returns
    -------
    manager : pluggy.PluginManager
    """
    manager = pluggy.PluginManager("docstub")
    manager.add_hookspecs(plugins)

    # Loading plugins via entrypoints is intentionally not supported (for now)
    # manager.load_setuptools_entrypoints("docstub")

    for path in paths:
        plugin_module = _import_standalone_module_from_path(path)
        manager.register(plugin_module)
        hooks = manager.get_hookcallers(plugin_module)
        logger.info("Registered plugin at %s (%i hook(s))", path, len(hooks))
        logger.debug("Hooks implemented by plugin at %s:\n%r", path, hooks)

    return manager


def _collect_type_info(root_path, *, ignore=(), cache=False):
    """Collect types.

    Parameters
    ----------
    root_path : Path
    ignore : Sequence[str], optional
        Don't yield files matching these glob-like patterns. The pattern is
        interpreted relative to the root of the Python package unless it starts
        with "/". See :func:`glob.translate` with recursion and hidden files
        enabled for more details on the precise implementation.
    cache : bool, optional
        Cache collected types.

    Returns
    -------
    types : dict[str, PyImport]
    type_prefixes : dict[str, PyImport]
    """
    types = common_known_types()

    if cache:
        collect = FileCache(
            func=TypeCollector.collect,
            serializer=TypeCollector.ImportSerializer(),
            cache_dir=cache_dir_in_cwd(),
        )
    else:
        collect = TypeCollector.collect

    collected_types = {}
    collected_type_prefixes = {}
    for source_path in walk_source_package(root_path, ignore=ignore):
        if cache:
            module = source_path.relative_to(root_path.parent)
            collect.sub_dir = f"{__version__}/{module}"

        types_in_file, prefixes_in_file = collect(source_path)
        collected_types.update(types_in_file)
        collected_type_prefixes.update(prefixes_in_file)

        logger.info(
            "Collected%s types in %s",
            " cached" if cache and collect.cached_last_call else "",
            source_path,
        )
        logger.debug(
            "%i types, %i type prefixes in %s",
            len(types_in_file),
            len(prefixes_in_file),
            source_path,
        )

    logger.debug("Collected %i types", len(collected_types))
    logger.debug("Collected %i type prefixes", len(collected_type_prefixes))
    types |= collected_types
    return types, collected_type_prefixes


@contextmanager
def _log_execution_time():
    """Measure and log execution time of wrapped function or block."""
    start = time.time()
    try:
        yield
    except KeyboardInterrupt:
        logger.critical("Interrupted!")
    finally:
        stop = time.time()
        total_seconds = stop - start

        hours, remainder = divmod(total_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)

        formated_duration = f"{seconds:.3f} s"
        if minutes:
            formated_duration = f"{minutes} min {formated_duration}"
        if hours:
            formated_duration = f"{hours} h {formated_duration}"

        logger.info("Finished in %s", formated_duration)


def _format_unknown_names(names):
    """Format unknown type names as a list for printing.

    Parameters
    ----------
    names : Iterable[str]

    Returns
    -------
    formatted : str
        A multiline string.

    Examples
    --------
    >>> names = ["path-like", "values", "arrays", "values"] + ["string"] * 11
    >>> print(_format_unknown_names(names))
    11  string
     2  values
     1  arrays
     1  path-like
    """
    counter = Counter(names)
    sorted_alphabetical = sorted(counter.items(), key=lambda x: x[0])
    sorted_by_frequency = sorted(sorted_alphabetical, key=lambda x: x[1], reverse=True)

    lines = []
    pad_left = len(str(sorted_by_frequency[0][1]))
    for item, count in sorted_by_frequency:
        count_fmt = f"{count}".rjust(pad_left)
        lines.append(f"{count_fmt}  {item}")
    formatted = "\n".join(lines)
    return formatted


def _generate_single_stub(task):
    """Transform a Python file into a stub file.

    Parameters
    ----------
    task : tuple[Path, Path, Py2StubTransformer]
        The `source_path` for which to create a stub file at `stub_path` with
        the given transformer.

    Returns
    -------
    stats : dict of {str: int or list[str]}
        Statistics about the transformation.
    """
    source_path, stub_path, stub_transformer = task

    if source_path.suffix.lower() == ".pyi":
        logger.debug("Using existing stub file %s", source_path)
        with source_path.open() as fo:
            stub_content = fo.read()
    else:
        with source_path.open() as fo:
            py_content = fo.read()
        logger.debug("Transforming %s", source_path)
        try:
            stub_content = stub_transformer.python_to_stub(
                py_content, module_path=source_path
            )
            stub_content = f"{STUB_HEADER_COMMENT}\n\n{stub_content}"
            stub_content = try_format_stub(stub_content)
        except Exception:
            logger.exception("Failed creating stub for %s", source_path)
            return None

    stub_path.parent.mkdir(parents=True, exist_ok=True)
    with stub_path.open("w") as fo:
        logger.info("Wrote %s", stub_path)
        fo.write(stub_content)

    stats = Stats.merge(
        stub_transformer.stats.pop_all(),
        stub_transformer.matcher.stats.pop_all(),
        stub_transformer.doctype_transpiler.stats.pop_all(),
    )

    return stats


@_log_execution_time()
def generate_stubs(
    *,
    root_path,
    out_dir,
    config_paths,
    ignore,
    group_errors,
    allow_errors,
    fail_on_warning,
    desired_worker_count,
    no_cache,
    verbosity,
):
    """Generate Python stub files (implementation of ``docstub run``).

    Parameters
    ----------
    root_path : Path
    out_dir : Path
    config_paths : Sequence[Path]
    ignore : Sequence[str]
    group_errors : bool
    allow_errors : int
    fail_on_warning : bool
    desired_worker_count : int
    no_cache : bool
    verbosity : {-2, -1, 0, 1, 2, 3}

    Returns
    -------
    exit_code : {0, 1}
    """
    output_handler, error_counter = setup_logging(
        verbosity=verbosity, group_errors=group_errors
    )

    logger.debug("Command line args: %s", sys.orig_argv)

    root_path = Path(root_path)
    if root_path.is_file():
        logger.warning(
            "Running docstub on a single module. Relative imports "
            "or type references pointing outside this module won't work."
        )
    elif find_package_root(root_path) != root_path.resolve():
        logger.warning(
            "Running docstub only on a subpackage. Relative imports "
            "or type references pointing outside this subpackage won't work."
        )

    config = _load_configuration(config_paths)
    config = config.merge(Config(ignore_files=list(ignore)))
    logger.debug("Fully loaded config:\n%s", config)

    plugin_manager = _load_plugins(config.plugin_paths)
    plugin_hooks = plugin_manager.hook

    types, type_prefixes = _collect_type_info(
        root_path, ignore=config.ignore_files, cache=not no_cache
    )

    # Add declared types from configuration
    types |= {
        type_name: PyImport(from_=module, import_=type_name)
        for type_name, module in config.types.items()
    }

    # Add declared type prefixes from configuration
    type_prefixes |= {
        prefix: (
            PyImport(import_=module, as_=prefix)
            if module != prefix
            else PyImport(import_=prefix)
        )
        for prefix, module in config.type_prefixes.items()
    }

    grammar = plugin_hooks.docstub_load_doctype_grammar()
    doctype_transformer = plugin_hooks.docstub_load_doctype_transformer()
    if (doctype_transformer and hasattr(doctype_transformer, "dtype_to_expand")) or (
        grammar and "dtype_to_expand" in grammar
    ):
        logger.warning(
            "The grammar rule 'dtype_to_expand' is deprecated in favor of 'dtype_union'",
            extra={
                "details": "It will be removed in v0.9.0. Since `numpy.dtype` supports "
                "unions, the rule was renamed. Use the rule 'dtype_union' if you want "
                "to modify this expression in a plugin."
            },
        )

    doctype_transpiler = doctype.DoctypeTranspiler(
        grammar=grammar, transformer=doctype_transformer
    )
    matcher = TypeMatcher(
        types=types, type_prefixes=type_prefixes, type_nicknames=config.type_nicknames
    )
    stub_transformer = Py2StubTransformer(
        matcher=matcher, doctype_transpiler=doctype_transpiler
    )

    if not out_dir:
        if root_path.is_file():
            out_dir = root_path.parent
        else:
            out_dir = root_path
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Stub generation ---------------------------------------------------------

    task_files = walk_source_and_targets(root_path, out_dir, ignore=config.ignore_files)

    # We must pass the `stub_transformer` to each worker, but we want to copy
    # only once per worker. Testing suggests, that using a large enough
    # `chunksize` of `>= len(task_count) / jobs` for `ProcessPoolExecutor.map`,
    # ensures that.
    # Using an `initializer` that assigns the transformer as a global variable
    # per worker seems like the more robust solution, but naive timing suggests
    # it's actually slower (> 1s on skimage).
    task_args = [(*files, stub_transformer) for files in task_files]
    task_count = len(task_args)

    worker_count, chunk_size = guess_concurrency_params(
        task_count=task_count, desired_worker_count=desired_worker_count
    )

    logger.info("Using %i worker(s) to write %i stubs", worker_count, task_count)
    logger.debug("Using chunk size of %i", chunk_size)
    with LoggingProcessExecutor(
        max_workers=worker_count,
        logging_handlers=(output_handler, error_counter),
    ) as executor:
        stats_per_task = executor.map(
            _generate_single_stub, task_args, chunksize=chunk_size
        )
        stats = Stats.merge(*stats_per_task)

    py_typed_out = out_dir / "py.typed"
    if not py_typed_out.exists():
        py_typed_out.touch()
        logger.info("Created %s", py_typed_out)

    # Reporting --------------------------------------------------------------

    if group_errors:
        output_handler.emit_grouped()
        assert output_handler.group_errors is True
        output_handler.group_errors = False

    # Report basic statistics
    logger.debug(
        "DoctypeTranspiler caching stats: hits=%i, misses=%i, maxsize=%i",
        stats.pop("doctype_transpiler_cache_hits", 0),
        stats.pop("doctype_transpiler_cache_misses", 0),
        max(stats.pop("doctype_transpiler_curr_cache_size", [0])),
    )
    logger.info("Recognized type names: %i", stats.pop("matched_type_names", 0))
    logger.info("Transformed doctypes: %i", stats.pop("transformed_doctypes", 0))

    total_warnings = error_counter.warning_count
    total_errors = error_counter.error_count
    if total_warnings:
        logger.warning("Warnings: %i", total_warnings)
    if "doctype_syntax_errors" in stats:
        assert total_errors
        logger.warning("Syntax errors: %i", stats.pop("doctype_syntax_errors"))
    if "unknown_type_names" in stats:
        assert total_errors
        logger.warning(
            "Unknown type names: %i (locations: %i)",
            len(set(stats["unknown_type_names"])),
            len(stats["unknown_type_names"]),
            extra={"details": _format_unknown_names(stats.pop("unknown_type_names"))},
        )
    if total_errors:
        logger.error("Total errors: %i", total_errors)

    assert len(stats) == 0, stats

    total_fails = total_errors
    if fail_on_warning:
        total_fails += total_warnings

    if allow_errors < total_fails:
        return 1
    return 0
