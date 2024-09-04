import itertools


def accumulate_qualname(qualname, *, start_right=False):
    """Return possible partial names from a fully qualified one.

    Examples
    --------
    >>> accumulate_qualname("a.b.c")
    ('a', 'a.b', 'a.b.c')
    >>> accumulate_qualname("a.b.c", start_right=True)
    ('c', 'b.c', 'a.b.c')
    """
    fragments = qualname.split(".")
    if start_right is True:
        fragments = reversed(fragments)
        template = "{1}.{0}"
    else:
        template = "{0}.{1}"
    out = tuple(
        itertools.accumulate(fragments, func=lambda x, y: template.format(x, y))
    )
    return out
