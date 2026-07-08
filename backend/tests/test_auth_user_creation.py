from types import SimpleNamespace

import pytest

from src.core.exceptions import BusinessValidationError, ForbiddenError
from src.models.tables import Threshold, User
from src.services.auth import create_user


class FakeSession:
    def __init__(self) -> None:
        self.added: list[object] = []
        self.commits = 0
        self.next_id = 101

    def add(self, item: object) -> None:
        self.added.append(item)

    async def flush(self) -> None:
        for item in self.added:
            if isinstance(item, User) and item.id is None:
                item.id = self.next_id
                self.next_id += 1

    async def commit(self) -> None:
        self.commits += 1


def _actor(role: str = "manager") -> User:
    return User(
        id=7,
        username="manager@sibionics.com",
        password="hashed",
        role=role,
        distributor_name="Manager Dealer",
    )


@pytest.mark.asyncio
async def test_manager_can_create_dealer_with_default_role(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = FakeSession()
    audits: list[dict[str, object]] = []

    async def fake_get_user_by_email(_db: object, email: str) -> None:
        assert email == "newdealer@sibionics.com"
        return None

    async def fake_record_audit_event(_db: object, **kwargs: object) -> None:
        audits.append(kwargs)

    monkeypatch.setattr("src.services.auth.get_user_by_email", fake_get_user_by_email)
    monkeypatch.setattr("src.services.auth.record_audit_event", fake_record_audit_event)

    user = await create_user(
        db,  # type: ignore[arg-type]
        actor=_actor(),
        email="  NewDealer@SIBIONICS.com  ",
        password="password123",
        distributor_name="  New Distributor  ",
    )

    assert user.id == 101
    assert user.username == "newdealer@sibionics.com"
    assert user.role == "dealer"
    assert user.distributor_name == "New Distributor"
    assert user.distributor_id is None
    assert user.password != "password123"
    assert any(isinstance(item, Threshold) and item.user_id == user.id for item in db.added)
    assert db.commits == 1
    assert audits == [
        {
            "user_id": 7,
            "action": "auth.user_created",
            "target_type": "user",
            "target_id": 101,
            "metadata": {
                "created_user_id": 101,
                "created_username": "newdealer@sibionics.com",
                "role": "dealer",
                "distributor_name": "New Distributor",
            },
        }
    ]


@pytest.mark.asyncio
async def test_manager_can_create_manager_role(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_get_user_by_email(_db: object, _email: str) -> None:
        return None

    async def fake_record_audit_event(_db: object, **_kwargs: object) -> None:
        return None

    monkeypatch.setattr("src.services.auth.get_user_by_email", fake_get_user_by_email)
    monkeypatch.setattr("src.services.auth.record_audit_event", fake_record_audit_event)

    user = await create_user(
        FakeSession(),  # type: ignore[arg-type]
        actor=_actor(),
        email="newmanager@sibionics.com",
        password="password123",
        role="manager",
        distributor_name="Manager Distributor",
    )

    assert user.role == "manager"


@pytest.mark.asyncio
async def test_dealer_cannot_create_users() -> None:
    with pytest.raises(ForbiddenError, match="Only manager users can create accounts."):
        await create_user(
            FakeSession(),  # type: ignore[arg-type]
            actor=_actor("dealer"),
            email="blocked@sibionics.com",
            password="password123",
            role="dealer",
            distributor_name="Blocked",
        )


@pytest.mark.asyncio
async def test_create_user_rejects_duplicate_email(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_get_user_by_email(_db: object, _email: str) -> SimpleNamespace:
        return SimpleNamespace(id=1)

    monkeypatch.setattr("src.services.auth.get_user_by_email", fake_get_user_by_email)

    with pytest.raises(BusinessValidationError, match="Email already exists."):
        await create_user(
            FakeSession(),  # type: ignore[arg-type]
            actor=_actor(),
            email="duplicate@sibionics.com",
            password="password123",
            role="dealer",
            distributor_name="Duplicate",
        )
