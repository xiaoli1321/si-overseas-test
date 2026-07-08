from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import BusinessValidationError, ForbiddenError, UnauthorizedError
from src.core.security import create_access_token, hash_password, verify_password
from src.models.tables import Threshold, User
from src.repositories.store import get_user_by_email
from src.rules.thresholds import default_thresholds
from src.services.analytics import track_login
from src.services.audit import record_audit_event


async def login(db: AsyncSession, email: str, password: str) -> tuple[str, User]:
    user = await get_user_by_email(db, email)
    if user is None:
        raise UnauthorizedError("Invalid email or password.")
    if not verify_password(password, user.password):
        await track_login(
            db, user=user, status="failure", fail_reason="invalid_password"
        )
        await db.commit()
        raise UnauthorizedError("Invalid email or password.")
    token = create_access_token(
        str(user.id), {"email": user.username, "role": user.role}
    )
    await track_login(db, user=user, status="success")
    await db.commit()
    return token, user


async def create_user(
    db: AsyncSession,
    *,
    actor: User,
    email: str,
    password: str,
    role: str = "dealer",
    distributor_name: str,
) -> User:
    if actor.role != "manager":
        raise ForbiddenError("Only manager users can create accounts.")
    if role not in {"manager", "dealer"}:
        raise BusinessValidationError("Role must be manager or dealer.")

    normalized_email = email.strip().lower()
    normalized_distributor_name = distributor_name.strip()
    if await get_user_by_email(db, normalized_email) is not None:
        raise BusinessValidationError("Email already exists.")

    user = User(
        distributor_id=None,
        distributor_name=normalized_distributor_name,
        username=normalized_email,
        password=hash_password(password),
        role=role,
    )
    db.add(user)
    await db.flush()

    db.add(
        Threshold(
            user_id=user.id,
            version=1,
            config_json=default_thresholds(),
            is_active=True,
        )
    )

    await record_audit_event(
        db,
        user_id=actor.id,
        action="auth.user_created",
        target_type="user",
        target_id=user.id,
        metadata={
            "created_user_id": user.id,
            "created_username": user.username,
            "role": user.role,
            "distributor_name": user.distributor_name,
        },
    )
    await db.commit()
    return user
