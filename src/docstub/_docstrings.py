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

from ._analysis import KnownImport, TypesDatabase
from ._utils import ContextFormatter, DocstubError, accumulate_qualname, escape_qualname

logger = logging.getLogger(__name__)


here = Path(__file__).parent
grammar_path = here / "doctype.lark"


with grammar_path.open() as file:
    _grammar = file.read()

_lark = lark.Lark(_grammar, propagate_positions=True)


def _find_one_token(tree: lark.Tree, *, name: str) -> lark.Token:
    """Find token with a specific type name in tree."""
    tokens = [child for child in tree.children if child.type == name]
    if len(tokens) != 1:
        msg = f"expected exactly one Token of type {name}, found {len(tokens)}"
        raise ValueError(msg)
    return tokens[0]


@dataclass(frozen=True, slots=True, kw_only=True)
class Annotation:
    """Python-ready type annotation with attached import information."""

    value: str
    imports: frozenset[KnownImport] = field(default_factory=frozenset)

    def __post_init__(self):
        object.__setattr__(self, "imports", frozenset(self.imports))
        if "~" in self.value:
            raise ValueError(f"unexpected '~' in annotation value: {self.value}")
        for import_ in self.imports:
            if not isinstance(import_, KnownImport):
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
        """Create new ``Generator`` type from yield, receive and return types.

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
        imports |= {KnownImport(import_path="typing", import_name="Generator")}
        generator = cls(value=value, imports=imports)
        return generator

    def as_optional(self):
        """Return optional version of this annotation by appending `| None`.

        Returns
        -------
        optional : Annotation

        Examples
        --------
        >>> Annotation(value="int").as_optional()
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
        imports : set[~.KnownImport]
        """
        values = []
        imports = set()
        for p in types:
            values.append(p.value)
            imports.update(p.imports)
        return values, imports


FallbackAnnotation = Annotation(
    value="Incomplete", imports=frozenset([KnownImport.typeshed_Incomplete()])
)


class QualnameIsKeyword(DocstubError):
    """Raised when a qualname is a blacklisted Python keyword."""


@lark.visitors.v_args(tree=True)
class DoctypeTransformer(lark.visitors.Transformer):
    """Transformer for docstring type descriptions (doctypes).

    Attributes
    ----------
    types_db : ~.TypesDatabase
    replace_doctypes : dict[str, str]
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

    def __init__(self, *, types_db=None, replace_doctypes=None, **kwargs):
        """
        Parameters
        ----------
        types_db : ~.TypesDatabase, optional
            A static database of collected types usable as an annotation. If
            not given, defaults to a database with common types from the
            standard library (see :func:`~.common_known_imports`).
        replace_doctypes : dict[str, str], optional
            Replacements for human-friendly aliases.
        kwargs : dict[Any, Any], optional
            Keyword arguments passed to the init of the parent class.
        """
        if replace_doctypes is None:
            replace_doctypes = {}
        if types_db is None:
            types_db = TypesDatabase()

        self.types_db = types_db
        self.replace_doctypes = replace_doctypes

        self._collected_imports = None
        self._unknown_qualnames = None

        super().__init__(**kwargs)

        self.stats = {"grammar_errors": 0}

    def doctype_to_annotation(self, doctype):
        """Turn a type description in a docstring into a type annotation.

        Parameters
        ----------
        doctype : str
            The doctype to parse.

        Returns
        -------
        annotation : Annotation
            The parsed annotation.
        unknown_qualnames : list[tuple[str, int, int]]
            A set containing tuples. Each tuple contains a qualname, its start and its
            end index relative to the given `doctype`.
        """
        try:
            self._collected_imports = set()
            self._unknown_qualnames = []
            tree = _lark.parse(doctype)
            value = super().transform(tree=tree)
            annotation = Annotation(
                value=value, imports=frozenset(self._collected_imports)
            )
            return annotation, self._unknown_qualnames
        except (
            lark.exceptions.LexError,
            lark.exceptions.ParseError,
            QualnameIsKeyword,
        ):
            self.stats["grammar_errors"] += 1
            raise
        finally:
            self._collected_imports = None
            self._unknown_qualnames = None

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
            out.type = data.upper()  # Turn rule into "token"
        else:
            out = children
        return out

    def annotation(self, tree):
        out = " | ".join(tree.children)
        return out

    def types_or(self, tree):
        out = " | ".join(tree.children)
        return out

    def optional(self, tree):
        logger.debug("dropping optional / default info")
        return lark.Discard

    def extra_info(self, tree):
        logger.debug("dropping extra info")
        return lark.Discard

    def sphinx_ref(self, tree):
        qualname = _find_one_token(tree, name="QUALNAME")
        return qualname

    def container(self, tree):
        _container, *_content = tree.children
        _content = ", ".join(_content)
        assert _content
        out = f"{_container}[{_content}]"
        return out

    def qualname(self, tree):
        children = tree.children
        _qualname = ".".join(children)

        for partial_qualname in accumulate_qualname(_qualname):
            replacement = self.replace_doctypes.get(partial_qualname)
            if replacement:
                _qualname = _qualname.replace(partial_qualname, replacement)
                break

        _qualname = self._match_import(_qualname, meta=tree.meta)

        if _qualname in self.blacklisted_qualnames:
            msg = (
                f"qualname {_qualname!r} in docstring type description "
                "is a reserved Python keyword and not allowed"
            )
            raise QualnameIsKeyword(msg)

        _qualname = lark.Token(type="QUALNAME", value=_qualname)
        return _qualname

    def array_name(self, tree):
        qualname = self.qualname(tree)
        qualname = lark.Token("ARRAY_NAME", str(qualname))
        return qualname

    def shape(self, tree):
        logger.debug("dropping shape information")
        return lark.Discard

    def shape_n_dtype(self, tree):
        name = _find_one_token(tree, name="ARRAY_NAME")
        children = [child for child in tree.children if child != name]
        if children:
            name = f"{name}[{', '.join(children)}]"
        return name

    def contains(self, tree):
        out = ", ".join(tree.children)
        out = f"[{out}]"
        return out

    def literals(self, tree):
        out = ", ".join(tree.children)
        out = f"Literal[{out}]"
        if self.types_db is not None:
            _, known_import = self.types_db.query("Literal")
            if known_import:
                self._collected_imports.add(known_import)
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
        if self.types_db is not None:
            annotation_name, known_import = self.types_db.query(qualname)
        else:
            annotation_name = None
            known_import = None

        if known_import and known_import.has_import:
            self._collected_imports.add(known_import)

        if annotation_name:
            matched_qualname = annotation_name
        else:
            # Unknown qualname, alias to `Incomplete`
            self._unknown_qualnames.append((qualname, meta.start_pos, meta.end_pos))
            matched_qualname = escape_qualname(qualname)
            any_alias = KnownImport(
                import_path="_typeshed",
                import_name="Incomplete",
                import_alias=matched_qualname,
            )
            self._collected_imports.add(any_alias)
        return matched_qualname


class DocstringAnnotations:
    """Collect annotations in a given docstring.

    Attributes
    ----------
    docstring : str
    transformer : DoctypeTransformer
    ctx : ~.ContextFormatter

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
    invalid syntax in doctype
        some invalid syntax
             ^
    <BLANKLINE>
    unknown name in doctype: 'unknown.symbol'
        unknown.symbol
        ^^^^^^^^^^^^^^
    <BLANKLINE>
    dict_keys(['a', 'b', 'c'])
    """

    def __init__(self, docstring, *, transformer, ctx=None):
        """
        Parameters
        ----------
        docstring : str
        transformer : DoctypeTransformer
        ctx : ~.ContextFormatter, optional
        """
        self.docstring = docstring
        self.np_docstring = npds.NumpyDocString(docstring)
        self.transformer = transformer

        if ctx is None:
            ctx = ContextFormatter(line=0)
        self.ctx: ContextFormatter = ctx

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
        ctx = self.ctx.with_line(offset=ds_line)

        try:
            annotation, unknown_qualnames = self.transformer.doctype_to_annotation(
                doctype
            )

        except (lark.exceptions.LexError, lark.exceptions.ParseError) as error:
            details = None
            if hasattr(error, "get_context"):
                details = error.get_context(doctype)
                details = details.replace("^", click.style("^", fg="red", bold=True))
            ctx.print_message("invalid syntax in doctype", details=details)
            return FallbackAnnotation

        except lark.visitors.VisitError as e:
            tb = "\n".join(traceback.format_exception(e.orig_exc))
            details = f"doctype: {doctype!r}\n\n{tb}"
            ctx.print_message("unexpected error while parsing doctype", details=details)
            return FallbackAnnotation

        else:
            for name, start_col, stop_col in unknown_qualnames:
                width = stop_col - start_col
                error_underline = click.style("^" * width, fg="red", bold=True)
                details = f"{doctype}\n{' ' * start_col}{error_underline}\n"
                ctx.print_message(f"unknown name in doctype: {name!r}", details=details)
            return annotation

    @cached_property
    def attributes(self):
        """Return the attributes found in the docstring.

        Returns
        -------
        attributes : dict[str, Annotation]
            A dictionary mapping attribute names to their annotations.
            Attributes without annotations fall back to :class:`_typeshed.Incomplete`.
        """
        annotations = {}
        for attribute in self.np_docstring["Attributes"]:
            self._handle_missing_whitespace(attribute)
            if not attribute.type:
                continue

            ds_line = 0
            for i, line in enumerate(self.docstring.split("\n")):
                if attribute.name in line and attribute.type in line:
                    ds_line = i
                    break

            if attribute.name in annotations:
                logger.warning("duplicate parameter name %r, ignoring", attribute.name)
                continue

            annotation = self._doctype_to_annotation(attribute.type, ds_line=ds_line)
            annotations[attribute.name.strip()] = annotation

        return annotations

    @cached_property
    def parameters(self) -> dict[str, Annotation]:
        """Return the parameters and "Other Parameters" found in the docstring.

        Returns
        -------
        parameters : dict[str, Annotation]
            A dictionary mapping parameters names to their annotations.
            Parameters without annotations fall back to :class:`_typeshed.Incomplete`.
        """
        param_section = self._get_section("Parameters")
        other_section = self._get_section("Other Parameters")

        duplicates = param_section.keys() & other_section.keys()
        for duplicate in duplicates:
            logger.warning("duplicate parameter name %r, ignoring", duplicate)

        # Last takes priority
        paramaters = other_section | param_section
        # Normalize *args & **kwargs
        paramaters = {name.strip(" *"): value for name, value in paramaters.items()}
        return paramaters

    @cached_property
    def returns(self):
        """Return the attributes found in the docstring.

        Returns
        -------
        return_annotation : Annotation | None
            The "return" annotation of a callable. If the docstring defines a
            "Yield" section, this will be a :class:`typing.Generator`.
        """
        out = self._yields or self._returns
        return out

    @cached_property
    def _returns(self) -> Annotation | None:
        out = self._get_section("Returns")
        if out:
            out = Annotation.many_as_tuple(out.values())
        else:
            out = None
        return out

    @cached_property
    def _yields(self) -> Annotation | None:
        yields = self._get_section("Yields")
        if not yields:
            return None

        receive_types = self._get_section("Receives")

        out = Annotation.as_generator(
            yield_types=yields.values(),
            receive_types=receive_types.values(),
            return_types=(self._returns,) if self._returns else (),
        )
        return out

    def _handle_missing_whitespace(self, param):
        """Handle missing whitespace between parameter and colon.

        In this case, NumPyDoc parses the entire thing as the parameter name and
        no annotation is detected. Since this typo can lead to very subtle & confusing
        bugs, let's warn users about it and attempt to handle it.

        Parameters
        ----------
        param : numpydoc.docscrape.Parameter

        Returns
        -------
        param : numpydoc.docscrape.Parameter
        """
        if ":" in param.name and param.type == "":
            msg = (
                "Possibly missing whitespace between parameter and colon in "
                "docstring, make sure to include it so that the type is parsed "
                "properly!"
            )
            hint = f"{param.name}"

            ds_line = 0
            for i, line in enumerate(self.docstring.split("\n")):
                if param.name in line:
                    ds_line = i
                    break
            ctx = self.ctx.with_line(offset=ds_line)
            ctx.print_message(msg, details=hint)

            new_name, new_type = param.name.split(":", maxsplit=1)
            param = npds.Parameter(name=new_name, type=new_type, desc=param.desc)

        return param

    def _get_section(self, name: str) -> dict[str, Annotation]:
        annotated_params = {}
        for param in self.np_docstring[name]:
            param = self._handle_missing_whitespace(param)  # noqa: PLW2901

            if param.name in annotated_params:
                # TODO make error
                logger.warning("duplicate parameter name %r, ignoring", param.name)
                continue

            if param.type:
                ds_line = self._find_docstring_line(param.name, param.type)
                annotation = self._doctype_to_annotation(param.type, ds_line=ds_line)
            else:
                annotation = FallbackAnnotation
            annotated_params[param.name.strip()] = annotation

        return annotated_params

    def _find_docstring_line(self, *patterns):
        line_count = 0
        for i, line in enumerate(self.docstring.split("\n")):
            if all(p in line for p in patterns):
                line_count = i
                break
        return line_count
