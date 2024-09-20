"""Transform types defined in docstrings to Python parsable types."""

import logging
import traceback
from dataclasses import dataclass, field
from functools import cached_property
from itertools import chain
from pathlib import Path

import lark
import lark.visitors
from numpydoc.docscrape import NumpyDocString

from ._analysis import KnownImport
from ._utils import ContextFormatter, accumulate_qualname, escape_qualname

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


GrammarErrorFallback = Annotation(
    value="_GrammarError_",
    imports=frozenset(
        (
            KnownImport(
                import_name="Any",
                import_path="typing",
                import_alias="_GrammarError_",
            ),
        )
    ),
)


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
        unknown_qualnames : set[tuple[str, int, int]]
            A set containing tuples. Each tuple contains a qualname, its start and its
            end index relative to the given `doctype`.
        """
        try:
            self._collected_imports = set()
            self._unknown_qualnames = set()
            tree = _lark.parse(doctype)
            value = super().transform(tree=tree)
            annotation = Annotation(
                value=value, imports=frozenset(self._collected_imports)
            )
            return annotation, self._unknown_qualnames
        except (lark.exceptions.LexError, lark.exceptions.ParseError):
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

        _qualname = self._find_import(_qualname, meta=tree.meta)

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
        _, known_import = self.inspector.query("Literal")
        if known_import:
            self._collected_imports.add(known_import)
        return out

    def _find_import(self, qualname, meta):
        """Match type names to known imports."""
        annotation_name, known_import = self.inspector.query(qualname)
        if known_import and known_import.has_import:
            self._collected_imports.add(known_import)
        if annotation_name:
            qualname = annotation_name
        else:
            # Unknown qualname, alias to `Any` and make visible
            self._unknown_qualnames.add((qualname, meta.start_pos, meta.end_pos))
            qualname = escape_qualname(qualname)
            any_alias = KnownImport(
                import_name="Any",
                import_path="typing",
                import_alias=qualname,
            )
            self._collected_imports.add(any_alias)
        return qualname


class DocstringAnnotations:
    def __init__(self, docstring, *, transformer, ctx=None):
        self.docstring = docstring
        self.np_docstring = NumpyDocString(docstring)
        self.transformer = transformer

        if ctx is None:
            ctx = ContextFormatter()
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
        ctx = self._ctx.with_line(offset=ds_line)

        try:
            annotation, unknown_qualnames = self.transformer.doctype_to_annotation(
                doctype
            )

        except (lark.exceptions.LexError, lark.exceptions.ParseError) as error:
            details = None
            if hasattr(error, "get_context"):
                details = error.get_context(doctype)
            ctx.print_message("doctype doesn't conform to grammar", details=details)
            return GrammarErrorFallback

        except lark.visitors.VisitError as e:
            tb = "\n".join(traceback.format_exception(e.orig_exc))
            details = f"doctype: {doctype!r}\n\n{tb}"
            ctx.print_message("unexpected error while parsing doctype", details=details)
            return GrammarErrorFallback

        else:
            for name, start_col, stop_col in unknown_qualnames:
                width = stop_col - start_col
                details = f"{doctype}\n{' ' * start_col}{'^' * width}\n"
                ctx.print_message(f"unknown name in doctype: {name!r}", details=details)
            return annotation

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

        if annotated_params:
            out = Annotation.as_return_tuple(annotated_params.values())
        else:
            out = None
        return out

    @cached_property
    def yields(self) -> Annotation | None:
        annotated_params = {}
        for param in self.np_docstring["Yields"]:
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

        if annotated_params:
            out = Annotation.as_return_tuple(annotated_params.values())
        else:
            out = None
        return out
