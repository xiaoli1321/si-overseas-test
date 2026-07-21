from typing import Protocol, TypeVar

from sqlalchemy import Select

from src.core.exceptions import NotFoundError


class UserScopedResource(Protocol):
    user_id: int


ScopedResourceT = TypeVar("ScopedResourceT", bound=UserScopedResource)


def apply_user_scope(
    query: Select, model: type[UserScopedResource], user_id: int
) -> Select:
    return query.where(model.user_id == user_id)


class AccountActor(Protocol):
    id: int
    role: str


def apply_scope_for_user(
    query: Select, model: type[UserScopedResource], actor: AccountActor
) -> Select:
    """Scope a query for the acting account.

    Managers operate across every account, so their queries are returned
    unfiltered. All other roles (e.g. dealer) stay restricted to rows they own.
    This is the shared primitive for cross-account manager views; the strict
    ``apply_user_scope`` above is kept for paths that must never widen.
    """
    if actor.role == "manager":
        return query
    return query.where(model.user_id == actor.id)


def require_user_scope(
    resource: ScopedResourceT | None, user_id: int, message: str
) -> ScopedResourceT:
    if resource is None or resource.user_id != user_id:
        raise NotFoundError(message)
    return resource
