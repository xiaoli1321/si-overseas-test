from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import UnauthorizedError
from src.core.security import create_access_token, verify_password
from src.models.tables import User
from src.repositories.store import get_user_by_email
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
