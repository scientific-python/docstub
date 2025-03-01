"""Transform types defined in docstrings to Python parsable types."""

import logging
import traceback
from dataclasses import dataclass, field
from functools import cached_property
from itertools import chain
from pathlib import Path

import click
import lark
import lark.visitors
from numpydoc.docscrape import NumpyDocString

from ._analysis import KnownImport
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
    def as_return_tuple(cls, return_types):
        """Concatenate multiple annotations and wrap in tuple if more than one.

        Useful to combine multiple returned types for a function into a single
        annotation.

        Parameters
        ----------
        return_types : Iterable[Annotation]
            The types to combine.

        Returns
        -------
        concatenated : Annotation
            The concatenated types.
        """
        values, imports = cls._aggregate_annotations(*return_types)
        value = ", ".join(values)
        if len(values) > 1:
            value = f"tuple[{value}]"
        concatenated = cls(value=value, imports=imports)
        return concatenated

    @classmethod
    def as_yields_generator(cls, yield_types, receive_types=()):
        """Create new iterator type from yield and receive types.

        Parameters
        ----------
        yield_types : Iterable[Annotation]
            The types to yield.
        receive_types : Iterable[Annotation], optional
            The types the generator receives.

        Returns
        -------
        iterator : Annotation
            The yielded and received types wrapped in a generator.
        """
        # TODO
        raise NotImplementedError()

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
    blacklisted_qualnames : frozenset[str]
        All Python keywords [1]_ are blacklisted from use in qualnames except for ``True``
        ``False`` and ``None``.

    References
    ----------
    .. [1] https://docs.python.org/3/reference/lexical_analysis.html#keywords

    Examples
    --------
    >>> transformer = DoctypeTransformer()
    >>> annotation, unknown_names = transformer.doctype_to_annotation("tuple of int")
    >>> annotation.value
    'tuple[int]'
    >>> unknown_names
    [('tuple', 0, 5), ('int', 9, 12)]
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
        types_db : ~.TypesDatabase
            A static database of collected types usable as an annotation.
        replace_doctypes : dict[str, str], optional
            Replacements for human-friendly aliases.
        kwargs : dict[Any, Any], optional
            Keyword arguments passed to the init of the parent class.
        """
        if replace_doctypes is None:
            replace_doctypes = {}

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
        children : list[lark.Token, ...]
            The children of the current node.
        meta : lark.tree.Meta
            Meta information for the current node.

        Returns
        -------
        out : lark.Token or list[lark.Token, ...]
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

        _qualname = self._find_import(_qualname, meta=tree.meta)

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

    def _find_import(self, qualname, meta):
        """Match type names to known imports."""
        if self.types_db is not None:
            annotation_name, known_import = self.types_db.query(qualname)
        else:
            annotation_name = None
            known_import = None

        if known_import and known_import.has_import:
            self._collected_imports.add(known_import)

        if annotation_name:
            qualname = annotation_name
        else:
            # Unknown qualname, alias to `Any` and make visible
            self._unknown_qualnames.append((qualname, meta.start_pos, meta.end_pos))
            qualname = escape_qualname(qualname)
            any_alias = KnownImport(
                import_path="_typeshed",
                import_name="Incomplete",
                import_alias=qualname,
            )
            self._collected_imports.add(any_alias)
        return qualname


class DocstringAnnotations:
    """Collect annotations in a given docstring.

    Examples
    --------
    >>> docstring = '''
    ... Parameters
    ... ----------
    ... a : tuple of int
    ... b : some invalid syntax
    ... c : unkown.symbol
    ... '''
    >>> transformer = DoctypeTransformer()
    >>> annotations = DocstringAnnotations(docstring, transformer=transformer)
    >>> annotations.parameters.keys()
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
        self.np_docstring = NumpyDocString(docstring)
        self.transformer = transformer

        self._ctx: ContextFormatter = ctx

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
        if self._ctx is not None:
            ctx = self._ctx.with_line(offset=ds_line)
        else:
            ctx = None

        try:
            annotation, unknown_qualnames = self.transformer.doctype_to_annotation(
                doctype
            )

        except (lark.exceptions.LexError, lark.exceptions.ParseError) as error:
            details = None
            if hasattr(error, "get_context"):
                details = error.get_context(doctype)
                details = details.replace("^", click.style("^", fg="red", bold=True))
            if ctx:
                ctx.print_message("invalid syntax in doctype", details=details)
            return FallbackAnnotation

        except lark.visitors.VisitError as e:
            tb = "\n".join(traceback.format_exception(e.orig_exc))
            details = f"doctype: {doctype!r}\n\n{tb}"
            if ctx:
                ctx.print_message(
                    "unexpected error while parsing doctype", details=details
                )
            return FallbackAnnotation

        else:
            for name, start_col, stop_col in unknown_qualnames:
                width = stop_col - start_col
                error_underline = click.style("^" * width, fg="red", bold=True)
                details = f"{doctype}\n{' ' * start_col}{error_underline}\n"
                if ctx:
                    ctx.print_message(
                        f"unknown name in doctype: {name!r}", details=details
                    )
            return annotation

    @cached_property
    def attributes(self) -> dict[str, Annotation]:
        annotations = {}
        for attribute in self.np_docstring["Attributes"]:
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
            annotations[attribute.name] = annotation

        return annotations

    @cached_property
    def parameters(self) -> dict[str, Annotation]:
        all_params = chain(
            self.np_docstring["Parameters"], self.np_docstring["Other Parameters"]
        )
        annotated_params = {}
        for param in all_params:
            if not param.type:
                continue

            ds_line = 0
            for i, line in enumerate(self.docstring.split("\n")):
                if param.name in line and param.type in line:
                    ds_line = i
                    break

            if param.name in annotated_params:
                logger.warning("duplicate parameter name %r, ignoring", param.name)
                continue

            annotation = self._doctype_to_annotation(param.type, ds_line=ds_line)
            annotated_params[param.name] = annotation

        return annotated_params

    @cached_property
    def returns(self) -> Annotation | None:
        annotated_params = {}
        for param in self.np_docstring["Returns"]:
            # NumPyDoc always requires a doctype for returns,
            assert param.type

            ds_line = 0
            for i, line in enumerate(self.docstring.split("\n")):
                if param.name in line and param.type in line:
                    ds_line = i
                    break

            if param.name in annotated_params:
                logger.warning("duplicate parameter name %r, ignoring", param.name)
                continue

            annotation = self._doctype_to_annotation(param.type, ds_line=ds_line)
            annotated_params[param.name] = annotation

        if annotated_params:
            out = Annotation.as_return_tuple(annotated_params.values())
        else:
            out = None
        return out
