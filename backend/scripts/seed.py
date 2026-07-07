import asyncio
import sys
from pathlib import Path

# Add backend dir to path
sys.path.append(str(Path(__file__).parent))

from src.core.database import create_all, AsyncSessionLocal
from src.services.bootstrap import ensure_seed_data


async def main():
    print("Creating all tables in the database...")
    await create_all()
    print("Ensuring seed data is populated...")
    async with AsyncSessionLocal() as db:
        await ensure_seed_data(db)
        await db.commit()
    print("Database seeding completed successfully.")


if __name__ == "__main__":
    asyncio.run(main())
