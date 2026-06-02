from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.security import hash_password
from src.models.tables import Distributor, Threshold, User
from src.repositories.store import get_active_threshold, get_user_by_email
from src.rules.thresholds import default_thresholds


from src.core.config import get_settings


async def ensure_seed_data(db: AsyncSession) -> None:
    settings = get_settings()

    # If the seed user already exists, use it — no need to create anything.
    user = await get_user_by_email(db, settings.seed_user_email)
    if user:
        threshold = await get_active_threshold(db, user.id)
        if threshold is None:
            db.add(
                Threshold(
                    user_id=user.id,
                    version=1,
                    config_json=default_thresholds(),
                    is_active=True,
                )
            )
        await db.commit()
        return

    # If there are already users in the database (e.g. manually inserted),
    # don't inject the seed user — assume the DB is externally managed.
    existing_count = await db.scalar(select(func.count(User.id)))
    if existing_count and existing_count > 0:
        return

    # Completely empty database — bootstrap with the default seed user.
    distributor = Distributor(
        name="Chris Overseas Dealer",
        distributor_type="Distributor",
    )
    db.add(distributor)
    await db.flush()

    user = User(
        distributor_id=distributor.id,
        distributor_name="Chris Overseas Dealer",
        username=settings.seed_user_email,
        password=hash_password(settings.seed_user_password),
        role="manager",
    )
    db.add(user)
    await db.flush()

    threshold = await get_active_threshold(db, user.id)
    if threshold is None:
        db.add(
            Threshold(
                user_id=user.id,
                version=1,
                config_json=default_thresholds(),
                is_active=True,
            )
        )
    await db.commit()
