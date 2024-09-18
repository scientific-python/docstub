"""Transform types defined in docstrings to Python parsable types."""

import logging
import textwrap
from dataclasses import dataclass, field
from functools import cached_property
from pathlib import Path

import click
import lark
import lark.visitors
from numpydoc.docscrape import NumpyDocString

from ._analysis import KnownImport
from ._utils import accumulate_qualname

logger = logging.getLogger(__name__)


here = Path(__file__).parent
grammar_path = here / "doctype.lark"


with grammar_path.open() as file:
    _grammar = file.read()

_lark = lark.Lark(_grammar)


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
        value = " , ".join(values)
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


ErrorFallbackAnnotation = Annotation(
    value="ErrorFallback",
    imports=frozenset(
        (
            KnownImport(
                import_name="Any",
                import_path="typing",
                import_alias="ErrorFallback",
            ),
        )
    ),
)


class KnownName(lark.Token):
    """Wrapper token signaling that a type name was matched to a known import."""


@lark.visitors.v_args(tree=True)
class DoctypeTransformer(lark.visitors.Transformer):
    """Transformer for docstring type descriptions (doctypes)."""

    def __init__(self, *, inspector, replace_doctypes, **kwargs):
        """
        Parameters
        ----------
        inspector : ~.StaticInspector
            A dictionary mapping atomic names used in doctypes to information such
            as where to import from or how to replace the name itself.
        replace_doctypes : dict[str, str]
        kwargs : dict[Any, Any]
            Keyword arguments passed to the init of the parent class.
        """
        self.inspector = inspector
        self.replace_doctypes = replace_doctypes
        self._collected_imports = None
        super().__init__(**kwargs)

    def transform(self, doctype):
        """Turn a type description in a docstring into a type annotation.

        Parameters
        ----------
        doctype : str
            The doctype to parse.

        Returns
        -------
        annotation : Annotation
            The parsed annotation.
        """
        try:
            self._collected_imports = set()
            tree = _lark.parse(doctype)
            value = super().transform(tree=tree)
            annotation = Annotation(
                value=value, imports=frozenset(self._collected_imports)
            )
            return annotation
        finally:
            self._collected_imports = None

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
        out = "None"
        literal = [child for child in tree.children if child.type == "LITERAL"]
        assert len(literal) <= 1
        if literal:
            out = lark.Discard  # Type should cover the default
        return out

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

        _qualname = self._find_import(_qualname)

        _qualname = lark.Token(type="QUALNAME", value=_qualname)
        return _qualname

    def ARRAY_NAME(self, token):
        assert "." not in token
        new_token = self.replace_doctypes.get(str(token), str(token))
        new_token = self._find_import(new_token)
        new_token = lark.Token(type="ARRAY_NAME", value=new_token)
        return new_token

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
        _, known_import = self.inspector.query("Literal")
        if known_import:
            self._collected_imports.add(known_import)
        return out

    def _find_import(self, qualname):
        """Match type names to known imports."""
        try:
            annotation_name, known_import = self.inspector.query(qualname)
            if known_import and known_import.has_import:
                self._collected_imports.add(known_import)
            if annotation_name:
                qualname = annotation_name
            else:
                logger.warning(
                    "unknown import for %r in %s",
                    qualname,
                    self.inspector.current_source,
                )
            return qualname
        except Exception as error:
            raise error


class DocstringAnnotations:
    def __init__(self, docstring, *, transformer, source=None):
        self.docstring = docstring
        self.np_docstring = NumpyDocString(docstring)
        self.transformer = transformer
        self.source = source

    def _format_grammar_error(self, error, doctype):
        msg = "doctype doesn't conform to grammar"
        details = doctype
        if hasattr(error, "get_context"):
            details = error.get_context(doctype)
        details = textwrap.indent(details, prefix="  ")
        out = f"{click.style(self.source, bold=True)} {msg}\n{details}"
        return out

    def _doctype_to_annotation(self, doctype):
        """Convert a type description to a Python-ready type.

        Parameters
        ----------
        doctype : str
            The type description of a parameter or return value, as extracted from
            a docstring.
        inspector : docstub._analysis.StaticInspector
        replace_doctypes : dict[str, str]

        Returns
        -------
        annotation : Annotation
            The transformed type, ready to be inserted into a stub file, with
            necessary imports attached.
        """
        try:
            annotation = self.transformer.transform(doctype)
            return annotation
        except (lark.exceptions.LexError, lark.exceptions.ParseError) as error:
            msg = self._format_grammar_error(error=error, doctype=doctype)
            click.echo(msg)
            return ErrorFallbackAnnotation
        except lark.visitors.VisitError as e:
            logger.exception(
                "unexpected error parsing doctype %r in %s, falling back to Any",
                doctype,
                self.source,
                exc_info=e.orig_exc,
            )
            return ErrorFallbackAnnotation

    @cached_property
    def parameters(self) -> dict[str, Annotation]:
        def name_and_type(numpydoc_section):
            name_type = {
                param.name: param.type
                for param in self.np_docstring[numpydoc_section]
                if param.type
            }
            return name_type

        params = name_and_type("Parameters")
        other = name_and_type("Other Parameters")

        duplicate_params = params.keys() & other.keys()
        if duplicate_params:
            raise ValueError(f"{duplicate_params=}")
        params.update(other)

        annotations = {
            name: self._doctype_to_annotation(type_) for name, type_ in params.items()
        }
        return annotations

    @cached_property
    def returns(self) -> Annotation | None:
        out = [
            self._doctype_to_annotation(param.type)
            for param in self.np_docstring["Returns"]
            if param.type
        ]
        out = Annotation.as_return_tuple(out) if out else None
        return out

    @cached_property
    def yields(self) -> Annotation | None:
        out = {
            self._doctype_to_annotation(param.type)
            for param in self.np_docstring["Yields"]
            if param.type
        }
        out = Annotation.as_return_tuple(out) if out else None
        return out
