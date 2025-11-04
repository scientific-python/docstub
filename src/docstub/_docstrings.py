"""Transform types defined in docstrings to Python parsable types."""

import logging
import traceback
from dataclasses import dataclass, field
from functools import cached_property
from pathlib import Path

import click
import lark
import lark.visitors
import numpydoc.docscrape as npds

# TODO Uncouple docstrings & analysis module
#   It should be possible to transform docstrings without matching to valid
#   types and imports. I think that could very well be done at a higher level,
#   e.g. in the stubs module.
from ._analysis import PyImport, TypeMatcher
from ._report import ContextReporter
from ._utils import DocstubError, escape_qualname

logger: logging.Logger = logging.getLogger(__name__)


here: Path = Path(__file__).parent
grammar_path: Path = here / "doctype.lark"


with grammar_path.open() as file:
    _grammar: str = file.read()

_lark: lark.Lark = lark.Lark(_grammar, propagate_positions=True, strict=True)


def _find_one_token(tree, *, name):
    """Find token with a specific type name in tree.

    Parameters
    ----------
    tree : lark.Tree
    name : str
        Name of the token to find in the children of `tree`.

    Returns
    -------
    token : lark.Token
    """
    tokens = [
        child
        for child in tree.children
        if hasattr(child, "type") and child.type == name
    ]
    if len(tokens) != 1:
        msg = f"expected exactly one Token of type {name}, found {len(tokens)}"
        raise ValueError(msg)
    return tokens[0]


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


class QualnameIsKeyword(DocstubError):
    """Raised when a qualname is a blacklisted Python keyword."""


@lark.visitors.v_args(tree=True)
class DoctypeTransformer(lark.visitors.Transformer):
    """Transformer for docstring type descriptions (doctypes).

    Attributes
    ----------
    matcher : ~.TypeMatcher
    stats : dict[str, Any]
    blacklisted_qualnames : ClassVar[frozenset[str]]
        All Python keywords [1]_ are blacklisted from use in qualnames except for ``True``
        ``False`` and ``None``.

    References
    ----------
    .. [1] https://docs.python.org/3/reference/lexical_analysis.html#keywords

    Examples
    --------
    >>> transformer = DoctypeTransformer()
    >>> annotation, unknown_names = transformer.doctype_to_annotation(
    ...     "tuple of (int or ndarray)"
    ... )
    >>> annotation.value
    'tuple[int | ndarray]'
    >>> unknown_names
    [('ndarray', 17, 24)]
    """

    blacklisted_qualnames = frozenset(
        {
            "await",
            "else",
            "import",
            "pass",
            "break",
            "except",
            "in",
            "raise",
            "class",
            "finally",
            "is",
            "return",
            "and",
            "continue",
            "for",
            "lambda",
            "try",
            "as",
            "def",
            "from",
            "nonlocal",
            "while",
            "assert",
            "del",
            "global",
            "not",
            "with",
            "async",
            "elif",
            "if",
            "or",
            "yield",
        }
    )

    def __init__(self, *, matcher=None, **kwargs):
        """
        Parameters
        ----------
        matcher : ~.TypeMatcher, optional
        kwargs : dict[Any, Any], optional
            Keyword arguments passed to the init of the parent class.
        """
        if matcher is None:
            matcher = TypeMatcher()

        self.matcher = matcher

        self._reporter = None
        self._collected_imports = None
        self._unknown_qualnames = None

        super().__init__(**kwargs)

        self.stats = {
            "doctype_syntax_errors": 0,
            "transformed_doctypes": 0,
        }

    def doctype_to_annotation(self, doctype, *, reporter=None):
        """Turn a type description in a docstring into a type annotation.

        Parameters
        ----------
        doctype : str
            The doctype to parse.
        reporter : ~.ContextReporter

        Returns
        -------
        annotation : Annotation
            The parsed annotation.
        unknown_qualnames : list[tuple[str, int, int]]
            A set containing tuples. Each tuple contains a qualname, its start and its
            end index relative to the given `doctype`.
        """
        try:
            self._reporter = reporter or ContextReporter(logger=logger)
            self._collected_imports = set()
            self._unknown_qualnames = []
            tree = _lark.parse(doctype)
            value = super().transform(tree=tree)
            annotation = Annotation(
                value=value, imports=frozenset(self._collected_imports)
            )
            self.stats["transformed_doctypes"] += 1
            return annotation, self._unknown_qualnames
        except (
            lark.exceptions.LexError,
            lark.exceptions.ParseError,
            QualnameIsKeyword,
        ):
            self.stats["doctype_syntax_errors"] += 1
            raise
        finally:
            self._reporter = None
            self._collected_imports = None
            self._unknown_qualnames = None

    def qualname(self, tree):
        """
        Parameters
        ----------
        tree : lark.Tree

        Returns
        -------
        out : lark.Token
        """
        children = tree.children
        _qualname = ".".join(children)

        _qualname = self._match_import(_qualname, meta=tree.meta)

        if _qualname in self.blacklisted_qualnames:
            msg = (
                f"qualname {_qualname!r} in docstring type description "
                "is a reserved Python keyword and not allowed"
            )
            raise QualnameIsKeyword(msg)

        _qualname = lark.Token(type="QUALNAME", value=_qualname)
        return _qualname

    def rst_role(self, tree):
        """
        Parameters
        ----------
        tree : lark.Tree

        Returns
        -------
        out : lark.Token
        """
        qualname = _find_one_token(tree, name="QUALNAME")
        return qualname

    def union(self, tree):
        """
        Parameters
        ----------
        tree : lark.Tree

        Returns
        -------
        out : str
        """
        out = " | ".join(tree.children)
        return out

    def subscription(self, tree):
        """
        Parameters
        ----------
        tree : lark.Tree

        Returns
        -------
        out : str
        """
        _container, *_content = tree.children
        _content = ", ".join(_content)
        assert _content
        out = f"{_container}[{_content}]"
        return out

    def natlang_literal(self, tree):
        """
        Parameters
        ----------
        tree : lark.Tree

        Returns
        -------
        out : str
        """
        out = ", ".join(tree.children)
        out = f"Literal[{out}]"

        if len(tree.children) == 1:
            self._reporter.warn(
                "Natural language literal with one item: `{%s}`",
                tree.children[0],
                details=f"Consider using `{out}` to improve readability",
            )

        if self.matcher is not None:
            _, py_import = self.matcher.match("Literal")
            if py_import.has_import:
                self._collected_imports.add(py_import)
        return out

    def natlang_container(self, tree):
        """
        Parameters
        ----------
        tree : lark.Tree

        Returns
        -------
        out : str
        """
        return self.subscription(tree)

    def natlang_array(self, tree):
        """
        Parameters
        ----------
        tree : lark.Tree

        Returns
        -------
        out : str
        """
        name = _find_one_token(tree, name="ARRAY_NAME")
        children = [child for child in tree.children if child != name]
        if children:
            name = f"{name}[{', '.join(children)}]"
        return str(name)

    def array_name(self, tree):
        """
        Parameters
        ----------
        tree : lark.Tree

        Returns
        -------
        out : lark.Token
        """
        # Treat `array_name` as `qualname`, but mark it as an array name,
        # so we know which one to treat as the container in `array_expression`
        # This currently relies on a hack that only allows specific names
        # in `array_expression` (see `ARRAY_NAME` terminal in gramar)
        qualname = self.qualname(tree)
        qualname = lark.Token("ARRAY_NAME", str(qualname))
        return qualname

    def shape(self, tree):
        """
        Parameters
        ----------
        tree : lark.Tree

        Returns
        -------
        out : lark.visitors._DiscardType
        """
        # self._reporter.debug("Dropping shape information %r", tree)
        return lark.Discard

    def optional_info(self, tree):
        """
        Parameters
        ----------
        tree : lark.Tree

        Returns
        -------
        out : lark.visitors._DiscardType
        """
        # self._reporter.debug("Dropping optional info %r", tree)
        return lark.Discard

    def __default__(self, data, children, meta):
        """Unpack children of rule nodes by default.

        Parameters
        ----------
        data : lark.Token
            The rule-token of the current node.
        children : list[lark.Token]
            The children of the current node.
        meta : lark.tree.Meta
            Meta information for the current node.

        Returns
        -------
        out : lark.Token or list[lark.Token]
            Either a token or list of tokens.
        """
        if isinstance(children, list) and len(children) == 1:
            out = children[0]
            if hasattr(out, "type"):
                out.type = data.upper()  # Turn rule into "token"
        else:
            out = children
        return out

    def _match_import(self, qualname, *, meta):
        """Match `qualname` to known imports or alias to "Incomplete".

        Parameters
        ----------
        qualname : str
        meta : lark.tree.Meta
            Location metadata for the `qualname`, used to report possible errors.

        Returns
        -------
        matched_qualname : str
            Possibly modified or normalized qualname.
        """
        if self.matcher is not None:
            annotation_name, py_import = self.matcher.match(qualname)
        else:
            annotation_name = None
            py_import = None

        if py_import and py_import.has_import:
            self._collected_imports.add(py_import)

        if annotation_name:
            matched_qualname = annotation_name
        else:
            # Unknown qualname, alias to `Incomplete`
            self._unknown_qualnames.append((qualname, meta.start_pos, meta.end_pos))
            matched_qualname = escape_qualname(qualname)
            any_alias = PyImport(
                from_="_typeshed",
                import_="Incomplete",
                as_=matched_qualname,
            )
            self._collected_imports.add(any_alias)
        return matched_qualname


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


class DocstringAnnotations:
    """Collect annotations in a given docstring.

    Attributes
    ----------
    docstring : str
    transformer : DoctypeTransformer
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
    >>> transformer = DoctypeTransformer()
    >>> annotations = DocstringAnnotations(docstring, transformer=transformer)
    >>> annotations.parameters.keys()
    dict_keys(['a', 'b', 'c'])
    """

    def __init__(self, docstring, *, transformer, reporter=None):
        """
        Parameters
        ----------
        docstring : str
        transformer : DoctypeTransformer
        reporter : ~.ContextReporter, optional
        """
        self.docstring = docstring
        self.np_docstring = npds.NumpyDocString(docstring)
        self.transformer = transformer

        if reporter is None:
            reporter = ContextReporter(logger=logger, line=0)
        self.reporter = reporter.copy_with(logger=logger)

    def _doctype_to_annotation(self, doctype, ds_line=0):
        """Convert a type description to a Python-ready type.

        Parameters
        ----------
        doctype : str
            The type description of a parameter or return value, as extracted from
            a docstring.
        ds_line : int, optional
            The line number relative to the docstring.

        Returns
        -------
        annotation : Annotation
            The transformed type, ready to be inserted into a stub file, with
            necessary imports attached.
        """
        reporter = self.reporter.copy_with(line_offset=ds_line)

        try:
            annotation, unknown_qualnames = self.transformer.doctype_to_annotation(
                doctype, reporter=reporter
            )
            reporter.debug(
                "Transformed doctype", details=("   %s\n-> %s", doctype, annotation)
            )

        except (lark.exceptions.LexError, lark.exceptions.ParseError) as error:
            details = None
            if hasattr(error, "get_context"):
                details = error.get_context(doctype)
                details = details.replace("^", click.style("^", fg="red", bold=True))
            reporter.error(
                "Invalid syntax in docstring type annotation", details=details
            )
            return FallbackAnnotation

        except lark.visitors.VisitError as e:
            tb = "\n".join(traceback.format_exception(e.orig_exc))
            details = f"doctype: {doctype!r}\n\n{tb}"
            reporter.error("Unexpected error while parsing doctype", details=details)
            return FallbackAnnotation

        else:
            for name, start_col, stop_col in unknown_qualnames:
                width = stop_col - start_col
                error_underline = click.style("^" * width, fg="red", bold=True)
                details = f"{doctype}\n{' ' * start_col}{error_underline}\n"
                reporter.error(f"Unknown name in doctype: {name!r}", details=details)
            return annotation

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
            annotation = self._doctype_to_annotation(param.type, ds_line=ds_line)
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
