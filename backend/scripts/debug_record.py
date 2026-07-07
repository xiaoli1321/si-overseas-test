import asyncio
import sys
from pathlib import Path
from sqlalchemy import select

sys.path.append(str(Path(__file__).parent))

from src.core.database import AsyncSessionLocal
from src.models.tables import DetectRecord
from src.rules.engine import run_rules
from src.rules.thresholds import default_thresholds
from src.integrations.overseas_client import OverseasCGMClient

async def main():
    async with AsyncSessionLocal() as db:
        res = await db.execute(select(DetectRecord).where(DetectRecord.id == 130))
        r = res.scalar_one_or_none()
        if r:
            print("=== RECORD 130 ===")
            print("SN:", r.serial_no)
            print("Status:", r.status)
            print("Verdict:", r.verdict)
            print("Subtype:", r.fault_subtype)
            print("Reasons:", r.reasons)
            
            # Fetch fresh device
            client = OverseasCGMClient()
            device = await client.get_device(r.serial_no)
            print("\nFresh Device fault field:", device.get("fault"))
            
            glucose = r.evidence["glucose_series"]
            alarm = {}
            file_ids = r.evidence["file_ids"]
            
            # Run rules locally
            result = run_rules(
                fault_category="Data accuracy",
                device=device,
                glucose_series=glucose,
                alarm=alarm,
                threshold_config=default_thresholds(),
                file_ids=file_ids,
            )
            print("\n=== LOCAL RULE RUN WITH FRESH DEVICE ===")
            print("Verdict:", result.verdict)
            print("Subtype:", result.fault_subtype)
            print("Reasons:", result.reasons)
            print("Matched Rules:", result.matched_rules)
            print("Evidence has vision_analysis:", "vision_analysis" in result.evidence)
        else:
            print("Record 130 not found.")

if __name__ == "__main__":
    asyncio.run(main())


