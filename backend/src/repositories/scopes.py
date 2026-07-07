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


def require_user_scope(
    resource: ScopedResourceT | None, user_id: int, message: str
) -> ScopedResourceT:
    if resource is None or resource.user_id != user_id:
        raise NotFoundError(message)
    return resource
