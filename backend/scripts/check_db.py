import asyncio
import sys
from pathlib import Path
from sqlalchemy import select

# Add backend dir to path
sys.path.append(str(Path(__file__).parent))

from src.core.database import AsyncSessionLocal
from src.models.tables import DetectRecord, User


async def main():
    async with AsyncSessionLocal() as db:
        res = await db.execute(select(User))
        users = res.scalars().all()
        print("--- USERS ---")
        for u in users:
            print(f"ID: {u.id}, Email: {u.email}, Distributor: {u.distributor_name}")

        res = await db.execute(select(DetectRecord))
        records = res.scalars().all()
        print("\n--- DETECT RECORDS ---")
        for r in records:
            print(
                f"ID: {r.id}, SN: {r.serial_no}, User ID: {r.user_id}, Status: {r.status}, "
                f"Verdict: {r.verdict}, Feedback: {r.feedback_status}, "
                f"Visible: {r.is_visible_in_workbench}"
            )


if __name__ == "__main__":
    asyncio.run(main())
