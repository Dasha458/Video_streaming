from typing import Any, Callable, List, Optional, Tuple, Type, TypeVar, cast

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

T = TypeVar("T")  # SQLAlchemy model type
U = TypeVar("U")


async def paginate_query(
    session: AsyncSession,
    model: Type[T],
    page: int = 1,
    size: int = 20,
    filters: Optional[List[Any]] = None,
    order_by: Any = None,
    preload: Optional[List[Any]] = None,
    mapper: Optional[Callable[[T], U]] = None,
    joins: Optional[List[Tuple[Any, Any]]] = None,
    count_from: Optional[Any] = None,
) -> Tuple[List[U], int]:
    """
    Generic pagination for SQLAlchemy async queries.

    ``joins`` lets the paginated rows come from ``model`` joined through an
    association table -- e.g. selecting ``Video`` rows via a
    ``VideoReaction`` link -- as a list of ``(target, onclause)`` pairs
    passed to ``.join()``. ``count_from`` overrides what the total count is
    computed over when it differs from ``model`` itself (e.g. counting
    ``VideoReaction`` rows while selecting the ``Video`` rows they point to).

    Returns: (items, total)
    """
    filters = filters or []
    preload = preload or []
    joins = joins or []

    total = (
        await session.scalar(
            select(func.count()).select_from(count_from or model).where(*filters)
        )
        or 0
    )

    stmt = select(model)
    for target, onclause in joins:
        stmt = stmt.join(target, onclause)
    stmt = stmt.where(*filters)
    for opt in preload:
        stmt = stmt.options(opt)
    if order_by is not None:
        stmt = stmt.order_by(order_by)

    stmt = stmt.offset((page - 1) * size).limit(size)
    result = await session.execute(stmt)
    raw_items = list(result.scalars().all())
    # Without a mapper the caller asked for the model rows themselves, so
    # U is T; mypy cannot express that relationship in one signature.
    items: List[U] = (
        [mapper(v) for v in raw_items]
        if mapper is not None
        else cast(List[U], raw_items)
    )
    return items, total
