"""Transform types defined in docstrings to Python parsable types."""

import logging
import traceback
import warnings
from dataclasses import dataclass, field
from functools import cached_property

import click
import lark
import lark.visitors
import numpydoc.docscrape as npds

# TODO Uncouple docstrings & analysis module
#   It should be possible to transform docstrings without matching to valid
#   types and imports. I think that could very well be done at a higher level,
#   e.g. in the stubs module.
from ._analysis import PyImport, TypeMatcher
from ._doctype import BlacklistedQualname, Term, TermKind, parse_doctype
from ._report import ContextReporter, Stats
from ._utils import escape_qualname

logger: logging.Logger = logging.getLogger(__name__)


def _update_qualnames(expr, *, _parents=()):
    """Yield and receive names in `expr`.

    This generator works as a coroutine.

    Parameters
    ----------
    expr : ~.Expr
    _parents : tuple of (~._doctype.Expr, ...)

    Yields
    ------
    parents : tuple of (~._doctype.Expr, ...)
    name : ~._doctype.Term

    Receives
    --------
    new_name : str

    Examples
    --------
    >>> from docstub._doctype import parse_doctype
    >>> expr = parse_doctype("tuple of (tuple or str, ...)")
    >>> updater = _update_qualnames(expr)
    >>> for parents, name in updater:
    ...     if name == "tuple" and parents[-1].rule == "union":
    ...         updater.send("list")
    ...     if name == "str":
    ...         updater.send("bytes")
    >>> expr.as_code()
    'tuple[list | bytes, ...]'
    """
    _parents += (expr,)
    children = expr.children.copy()

    for i, child in enumerate(children):
        if hasattr(child, "children"):
            yield from _update_qualnames(child, _parents=_parents)

        elif child.kind == TermKind.NAME:
            new_name = yield _parents, child
            if new_name is not None:
                new_term = Term(new_name, kind=child.kind)
                expr.children[i] = new_term
                # `send` was called, yield `None` to return from `send`,
                # otherwise send would return the next child
                yield


@dataclass(frozen=True, slots=True, kw_only=True)
class Annotation:
    """Python-ready type annotation with attached import information."""

    value: str
    imports: frozenset[PyImport] = field(default_factory=frozenset)

    def __post_init__(self):
        object.__setattr__(self, "imports", frozenset(self.imports))
        if "~" in self.value:
            raise ValueError(f"unexpected '~' in annotation value: {self.value}")
        for import_ in self.imports:
            if not isinstance(import_, PyImport):
                raise TypeError(f"unexpected type {type(import_)} in `imports`")

    def __str__(self) -> str:
        return self.value

    @classmethod
    def many_as_tuple(cls, types):
        """Concatenate multiple annotations and wrap in tuple if more than one.

        Useful to combine multiple returned types for a function into a single
        annotation.

        Parameters
        ----------
        types : Iterable[Annotation]
            The types to combine.

        Returns
        -------
        concatenated : Annotation
            The concatenated types.
        """
        values, imports = cls._aggregate_annotations(*types)
        value = ", ".join(values)
        if len(values) > 1:
            value = f"tuple[{value}]"
        concatenated = cls(value=value, imports=imports)
        return concatenated

    @classmethod
    def as_generator(cls, *, yield_types, receive_types=(), return_types=()):
        """Create copy_with ``Generator`` type from yield, receive and return types.

        Parameters
        ----------
        yield_types : Iterable[Annotation]
            The types to yield.
        receive_types : Iterable[Annotation], optional
            The types the generator receives.
        return_types : Iterable[Annotation], optional
            The types the generator function returns.

        Returns
        -------
        generator : Annotation
            The provided types wrapped in a ``Generator``.
        """
        yield_annotation = cls.many_as_tuple(yield_types)
        imports = yield_annotation.imports
        value = yield_annotation.value

        if receive_types:
            receive_annotation = cls.many_as_tuple(receive_types)
            imports |= receive_annotation.imports
            value = f"{value}, {receive_annotation.value}"
        elif return_types:
            # Append None, so that return types are at correct position
            value = f"{value}, None"

        if return_types:
            return_annotation = cls.many_as_tuple(return_types)
            imports |= return_annotation.imports
            value = f"{value}, {return_annotation.value}"

        value = f"Generator[{value}]"
        imports |= {PyImport(from_="collections.abc", import_="Generator")}
        generator = cls(value=value, imports=imports)
        return generator

    def as_union_with_none(self):
        """Return a union with `| None` of the current annotation.

        .. note::
            Doesn't check for `| None` or `Optional[...]` being present.

        Returns
        -------
        union : Annotation

        Examples
        --------
        >>> Annotation(value="int").as_union_with_none()
        Annotation(value='int | None', imports=frozenset())
        """
        # TODO account for `| None` or `Optional` already being included?
        value = f"{self.value} | None"
        optional = type(self)(value=value, imports=self.imports)
        return optional

    @staticmethod
    def _aggregate_annotations(*types):
        """Aggregate values and imports of given Annotations.

        Parameters
        ----------
        types : Iterable[Annotation]

        Returns
        -------
        values : list[str]
        imports : set[PyImport]
        """
        values = []
        imports = set()
        for p in types:
            values.append(p.value)
            imports.update(p.imports)
        return values, imports


FallbackAnnotation: Annotation = Annotation(
    value="Incomplete", imports=frozenset([PyImport.typeshed_Incomplete()])
)


def _uncombine_numpydoc_params(params):
    """Split combined NumPyDoc parameters.

    NumPyDoc allows joining multiple parameters with shared type on one line.
    This function helps with iterating them one-by-one regardless.

    Parameters
    ----------
    params : list[npds.Parameter]

    Yields
    ------
    param : npds.Parameter
    """
    for param in params:
        if "," in param.name:
            # Multiple parameters on one line, split and yield separately
            names = [p.strip() for p in param.name.split(",")]
            for name in names:
                # Uncombined parameter re-uses shared type and description
                uncombined = npds.Parameter(name=name, type=param.type, desc=param.desc)
                yield uncombined
        else:
            yield param


def _red_partial_underline(doctype, *, start, stop):
    """Underline a part of a string with red '^'.

    Parameters
    ----------
    doctype : str
    start : int
    stop : int

    Returns
    -------
    underlined : str
    """
    width = stop - start
    assert width > 0
    underline = click.style("^" * width, fg="red", bold=True)
    underlined = f"{doctype}\n{' ' * start}{underline}\n"
    return underlined


def doctype_to_annotation(doctype, *, matcher=None, reporter=None, stats=None):
    """Convert a type description to a Python-ready type.

    Parameters
    ----------
    doctype : str
    matcher : ~.TypeMatcher, optional
    reporter : ~.ContextReporter, optional
    stats : ~.Stats, optional

    Returns
    -------
    annotation : Annotation
        The transformed type, ready to be inserted into a stub file, with
        necessary imports attached.
    """
    matcher = matcher or TypeMatcher()
    reporter = reporter or ContextReporter(logger=logger)
    stats = Stats() if stats is None else stats

    try:
        expression = parse_doctype(doctype, reporter=reporter)
        stats.inc_counter("transformed_doctypes")
        reporter.debug(
            "Transformed doctype", details=("   %s\n-> %s", doctype, expression)
        )

        imports = set()
        unknown_qualnames = set()
        updater = _update_qualnames(expression)
        for _, name in updater:
            search_name = str(name)
            matched_name, py_import = matcher.match(search_name)
            if matched_name is None:
                assert py_import is None
                unknown_qualnames.add((search_name, *name.pos))
                matched_name = escape_qualname(search_name)
            _ = updater.send(matched_name)
            assert _ is None

            if py_import is None:
                incomplete_alias = PyImport(
                    from_="_typeshed",
                    import_="Incomplete",
                    as_=matched_name,
                )
                imports.add(incomplete_alias)
            elif py_import.has_import:
                imports.add(py_import)

        annotation = Annotation(value=str(expression), imports=frozenset(imports))

    except (
        lark.exceptions.LexError,
        lark.exceptions.ParseError,
    ) as error:
        details = None
        if hasattr(error, "get_context"):
            details = error.get_context(doctype)
            details = details.replace("^", click.style("^", fg="red", bold=True))
        stats.inc_counter("doctype_syntax_errors")
        reporter.error("Invalid syntax in docstring type annotation", details=details)
        return FallbackAnnotation

    except lark.visitors.VisitError as error:
        original_error = error.orig_exc
        if isinstance(original_error, BlacklistedQualname):
            msg = "Blacklisted keyword argument in doctype"
            details = _red_partial_underline(
                doctype,
                start=error.obj.meta.start_pos,
                stop=error.obj.meta.end_pos,
            )
        else:
            msg = "Unexpected error while parsing doctype"
            tb = traceback.format_exception(original_error)
            tb = "\n".join(tb)
            details = f"doctype: {doctype!r}\n\n{tb}"
        reporter.error(msg, details=details)
        return FallbackAnnotation

    else:
        for name, start_col, stop_col in unknown_qualnames:
            details = _red_partial_underline(doctype, start=start_col, stop=stop_col)
            reporter.error(f"Unknown name in doctype: {name!r}", details=details)
        return annotation


class DocstringAnnotations:
    """Collect annotations in a given docstring.

    Attributes
    ----------
    docstring : str
    matcher : ~.TypeMatcher
    reporter : ~.ContextReporter

    Examples
    --------
    >>> docstring = '''
    ... Parameters
    ... ----------
    ... a : tuple of int
    ... b : some invalid syntax
    ... c : unknown.symbol
    ... '''
    >>> annotations = DocstringAnnotations(docstring)
    >>> annotations.parameters.keys()
    dict_keys(['a', 'b', 'c'])
    """

    def __init__(self, docstring, *, matcher=None, reporter=None, stats=None):
        """
        Parameters
        ----------
        docstring : str
        matcher : ~.TypeMatcher, optional
        reporter : ~.ContextReporter, optional
        stats : ~.Stats, optional
        """
        self.docstring = docstring
        self.matcher = matcher or TypeMatcher()
        self.stats = Stats() if stats is None else stats

        if reporter is None:
            reporter = ContextReporter(logger=logger, line=0)
        self.reporter = reporter.copy_with(logger=logger)

        with warnings.catch_warnings(record=True) as records:
            self.np_docstring = npds.NumpyDocString(docstring)
        for message in records:
            short = "Warning in NumPyDoc while parsing docstring"
            details = message.message.args[0]
            self.reporter.warn(short, details=details)

    @cached_property
    def attributes(self):
        """Return the attributes found in the docstring.

        Returns
        -------
        attributes : dict[str, Annotation]
            A dictionary mapping attribute names to their annotations.
            Attributes without annotations fall back to
            :class:`FallbackAnnotation` which corresponds to
            :class:`_typeshed.Incomplete`.
        """
        annotations = self._section_annotations("Attributes")
        return annotations

    @cached_property
    def parameters(self):
        """Return the parameters and "Other Parameters" found in the docstring.

        Returns
        -------
        parameters : dict[str, Annotation]
            A dictionary mapping parameters names to their annotations.
            Parameters without annotations fall back to
            :class:`FallbackAnnotation` which corresponds to
            :class:`_typeshed.Incomplete`.
        """
        param_section = self._section_annotations("Parameters")
        other_section = self._section_annotations("Other Parameters")

        duplicates = param_section.keys() & other_section.keys()
        for duplicate in duplicates:
            self.reporter.warn(
                "Duplicate attribute name in docstring",
                details=self.reporter.underline(duplicate),
            )

        # Last takes priority
        paramaters = other_section | param_section
        # Normalize *args & **kwargs
        paramaters = {name.strip(" *"): value for name, value in paramaters.items()}
        return paramaters

    @cached_property
    def returns(self):
        """Return annotation of the callable documented in the docstring.

        Returns
        -------
        return_annotation : Annotation | None
            The "return" annotation of a callable. If the docstring defines a
            "Yield" section, this will be a :class:`typing.Generator`.
        """
        out = self._yields or self._returns
        return out

    @cached_property
    def _returns(self):
        """Annotation of the "Return" section in the docstring.

        Returns
        -------
        return_annotation : Annotation | None
            The "return" annotation. If the section contains multiple entries,
            they are concatenated inside a tuple.
        """
        out = self._section_annotations("Returns")
        if out:
            out = Annotation.many_as_tuple(out.values())
        else:
            out = None
        return out

    @cached_property
    def _yields(self):
        """Annotations of the docstring's "Yields", "Receives" and "Returns" sections.

        Returns
        -------
        yield_annotation : Annotation | None
            The annotations from "Yields", "Receives" and "Returns" sections aggregated
            in a :class`typing.Generator`.
        """
        yields = self._section_annotations("Yields")
        if not yields:
            return None

        receive_types = self._section_annotations("Receives")

        yield_annotation = Annotation.as_generator(
            yield_types=yields.values(),
            receive_types=receive_types.values(),
            return_types=(self._returns,) if self._returns else (),
        )
        return yield_annotation

    def _handle_missing_whitespace(self, param):
        """Handle missing whitespace between parameter and colon.

        In this case, NumPyDoc parses the entire thing as the parameter name and
        no annotation is detected. Since this typo can lead to very subtle & confusing
        bugs, let's warn users about it and attempt to handle it.

        Parameters
        ----------
        param : npds.Parameter

        Returns
        -------
        param : npds.Parameter
        """
        if ":" in param.name and param.type == "":
            msg = "Possibly missing whitespace between parameter and colon in docstring"
            underline = "".join("^" if c == ":" else " " for c in param.name)
            underline = click.style(underline, fg="red", bold=True)
            hint = (
                f"{param.name}\n{underline}"
                f"\nInclude whitespace so that the type is parsed properly!"
            )

            ds_line = 0
            for i, line in enumerate(self.docstring.split("\n")):
                if param.name in line:
                    ds_line = i
                    break
            reporter = self.reporter.copy_with(line_offset=ds_line)
            reporter.warn(msg, details=hint)

            new_name, new_type = param.name.split(":", maxsplit=1)
            param = npds.Parameter(name=new_name, type=new_type, desc=param.desc)

        return param

    def _section_annotations(self, name):
        """Return the parameters of a specific section found in the docstring.

        Parameters
        ----------
        name : str
            Name of the specific section.

        Returns
        -------
        annotations : dict[str, Annotation]
            A dictionary mapping names to their annotations.
            Entries without annotations fall back to :class:`_typeshed.Incomplete`.
        """
        annotated_params = {}

        params = self.np_docstring[name]
        params = list(_uncombine_numpydoc_params(params))
        for param in params:
            param = self._handle_missing_whitespace(param)  # noqa: PLW2901

            if param.type.strip() == "":
                # Missing doctype in docstring, might have an inlined annotation
                # so skip
                continue

            if param.name in annotated_params:
                self.reporter.warn(
                    "Duplicate parameter / attribute name in docstring",
                    details=self.reporter.underline(param.name),
                )
                continue

            ds_line = self._find_docstring_line(param.name, param.type)

            annotation = doctype_to_annotation(
                doctype=param.type,
                matcher=self.matcher,
                reporter=self.reporter.copy_with(line_offset=ds_line),
                stats=self.stats,
            )
            annotated_params[param.name.strip()] = annotation

        return annotated_params

    def _find_docstring_line(self, *substrings):
        """Find line with all given substrings.

        Parameters
        ----------
        *substrings : str
            Naive substrings to search for.

        Returns
        -------
        line_number : int
            The number of the first line that contains all given `substrings`.
            Defaults to 0 if `substrings` never match.
        """
        line_number = 0
        for i, line in enumerate(self.docstring.split("\n")):
            if all(p in line for p in substrings):
                line_number = i
                break
        return line_number
