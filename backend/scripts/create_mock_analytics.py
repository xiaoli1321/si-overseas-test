import asyncio
import sys
from pathlib import Path
from datetime import datetime, UTC, timedelta
import random

# Ensure backend source is in python path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.core.database import AsyncSessionLocal
from src.models.tables import User, Distributor, AuditLog, DetectRecord, Threshold
from src.rules.thresholds import default_thresholds
from sqlalchemy import select, delete

async def get_or_create_distributor(db, name, dist_type):
    res = await db.execute(select(Distributor).where(Distributor.name == name))
    dist = res.scalar_one_or_none()
    if not dist:
        dist = Distributor(name=name, distributor_type=dist_type)
        db.add(dist)
        await db.flush()
    return dist

async def get_or_create_user(db, username, role, dist):
    res = await db.execute(select(User).where(User.username == username))
    user = res.scalar_one_or_none()
    if not user:
        user = User(
            username=username,
            password="pbkdf2_sha256$260000$mockpasswordhash", # mock hash
            role=role,
            distributor_id=dist.id,
            distributor_name=dist.name
        )
        db.add(user)
        await db.flush()
    return user

async def main():
    print("Connecting to database to insert mock analytics data...")
    async with AsyncSessionLocal() as db:
        # 1. Create/get mock distributors
        # 0. Rename old distributors to countries if they exist
        rename_map = {
            "Alpha Medical Supplies": "Germany",
            "Beta Health Corp": "United Kingdom",
            "Chris Overseas Dealer": "France"
        }
        for old_name, new_name in rename_map.items():
            res = await db.execute(select(Distributor).where(Distributor.name == new_name))
            if not res.scalar_one_or_none():
                res_old = await db.execute(select(Distributor).where(Distributor.name == old_name))
                old_dist = res_old.scalar_one_or_none()
                if old_dist:
                    old_dist.name = new_name
                    db.add(old_dist)
                    await db.flush()
                    res_users = await db.execute(select(User).where(User.distributor_id == old_dist.id))
                    for u in res_users.scalars().all():
                        u.distributor_name = new_name
                        db.add(u)
                    await db.flush()

        # 1. Create/get mock distributors
        dist_a = await get_or_create_distributor(db, "Germany", "Level 1 Dealer")
        dist_b = await get_or_create_distributor(db, "United Kingdom", "Level 2 Dealer")
        dist_chris = await get_or_create_distributor(db, "France", "Level 1 Dealer")
        
        # 2. Create/get mock users
        user_a = await get_or_create_user(db, "alpha_dealer@test.com", "dealer", dist_a)
        user_b = await get_or_create_user(db, "beta_dealer@test.com", "dealer", dist_b)
        
        # We also use the existing user if available
        res_chris = await db.execute(select(User).where(User.username == "christest@sibionics.com"))
        user_chris = res_chris.scalar_one_or_none()
        users = [user_a, user_b]
        if user_chris:
            if user_chris.distributor_id != dist_chris.id or user_chris.distributor_name != dist_chris.name:
                user_chris.distributor_id = dist_chris.id
                user_chris.distributor_name = dist_chris.name
                db.add(user_chris)
                await db.flush()
            users.append(user_chris)
            
        print(f"Using users for mock logs: {[u.username for u in users]}")

        # Clean up existing mock logs/records of this script to avoid infinite growth
        # We delete logs belonging to our mock users for these actions
        user_ids = [u.id for u in users]
        
        # Let's delete all audit logs for these user IDs with our target actions
        target_actions = ["auth.login", "device.query", "diagnosis.completed", "verdict.adoption", "threshold.modify"]
        await db.execute(
            delete(AuditLog)
            .where(AuditLog.user_id.in_(user_ids))
            .where(AuditLog.action.in_(target_actions))
        )
        # Delete detect records created for mock users to reset adoption rate testing
        await db.execute(
            delete(DetectRecord)
            .where(DetectRecord.user_id.in_(user_ids))
        )
        await db.commit()
        print("Cleaned up previous mock records and audit logs for target users.")

        # 3. Create mock login records (auth.login)
        # Let's generate 400 successful logins and 100 failed logins
        print("Inserting mock logins...")
        now = datetime.now(UTC)
        for _ in range(500):
            user = random.choice(users)
            status = "success" if random.random() > 0.2 else "failure"
            fail_reason = "invalid_password" if status == "failure" else None
            created_at = now - timedelta(days=random.randint(0, 15), hours=random.randint(0, 23))
            
            log = AuditLog(
                user_id=user.id,
                action="auth.login",
                target_type="user",
                target_id=str(user.id),
                status=status,
                event_metadata={
                    "user_id": user.id,
                    "username": user.username,
                    "role": user.role,
                    "distributor_id": user.distributor_id,
                    "distributor_name": user.distributor_name,
                    "status": status,
                    "fail_reason": fail_reason
                },
                created_at=created_at
            )
            db.add(log)

        from src.integrations.mock_cgm import MOCK_DEVICES
        mock_devices_list = list(MOCK_DEVICES.values())
        mock_sns = list(MOCK_DEVICES.keys())

        # 4. Create mock device query records (device.query)
        print("Inserting mock device queries...")
        query_types = ["single", "search", "batch"]
        for _ in range(400):
            user = random.choice(users)
            q_type = random.choice(query_types)
            batch_count = random.randint(2, 20) if q_type == "batch" else 1
            created_at = now - timedelta(days=random.randint(0, 15), hours=random.randint(0, 23))
            selected_sns = [random.choice(mock_sns) for _ in range(batch_count)]
            
            log = AuditLog(
                user_id=user.id,
                action="device.query",
                target_type="device",
                target_id=selected_sns[0],
                status="success",
                event_metadata={
                    "user_id": user.id,
                    "username": user.username,
                    "role": user.role,
                    "distributor_id": user.distributor_id,
                    "distributor_name": user.distributor_name,
                    "entry_source": random.choice(["shortcut", "recommendation"]),
                    "fault_category": random.choice(["Data accuracy", "Sensor falling off", "Sensor Abnormal", "Application failure"]),
                    "query_type": q_type,
                    "serial_no": selected_sns[0],
                    "batch_count": batch_count,
                    "query_count": batch_count,
                    "serial_nos": selected_sns
                },
                created_at=created_at
            )
            db.add(log)

        # 5. Create mock diagnosis records in detect_records and diagnosis.completed logs
        print("Inserting mock detect records & diagnosis.completed logs...")
        sources = ["AI (VLM)", "Rule Engine"]
        adoption_statuses = ["adopted", "rejected", "none"]
        reject_reasons = ["诊断不准确", "建议方案错误", "流程繁琐", "用户拒绝提供凭证"]
        
        for i in range(1000):
            user = random.choice(users)
            
            # Pick a random mock device to base our record on
            m_dev = random.choice(mock_devices_list)
            sn = m_dev["sn"]
            cat = m_dev["fault"]["faultCategory"]
            sub = m_dev["fault"]["faultSubtype"]
            verdict = m_dev["fault"]["expectedAfterSales"]
            
            if cat == "Application failure":
                if verdict == "Replacement Eligible":
                    sub = random.choice([
                        "Assembly failed",
                        "Guiding needle retention",
                        "Exposed Electrodes",
                        "Adhesive detaching",
                        "Implanter damage"
                    ])
                else:
                    sub = "No Application Failure"
            
            source = random.choice(sources)
            adopt = random.choice(adoption_statuses)
            reason = random.choice(reject_reasons) if adopt == "rejected" else None
            
            created_at = now - timedelta(days=random.randint(0, 15), hours=random.randint(0, 23))
            
            # Insert DetectRecord
            rec = DetectRecord(
                user_id=user.id,
                distributor_id=user.distributor_id,
                serial_no=sn,
                device_type="GS1",
                fault_category=cat,
                fault_subtype=sub,
                status="completed",
                verdict=verdict,
                issue_detected="Issue Detected" if verdict == "Replacement Eligible" else "no issue",
                adoption_status=adopt,
                reject_reason=reason,
                created_by=user.id,
                created_at=created_at,
                completed_at=created_at
            )
            db.add(rec)
            await db.flush() # Populate record.id
            
            # Insert diagnosis.completed log
            log = AuditLog(
                user_id=user.id,
                action="diagnosis.completed",
                target_type="detect_record",
                target_id=str(rec.id),
                status="success",
                event_metadata={
                    "user_id": user.id,
                    "username": user.username,
                    "role": user.role,
                    "distributor_id": user.distributor_id,
                    "distributor_name": user.distributor_name,
                    "record_id": rec.id,
                    "serial_no": rec.serial_no,
                    "fault_category": cat,
                    "fault_subtype": sub,
                    "verdict": verdict,
                    "judgment_source": source,
                    "has_images": random.choice([True, False])
                },
                created_at=created_at
            )
            db.add(log)

        # 6. Create mock threshold sensitivity logs (threshold.modify)
        print("Inserting mock threshold modify events...")
        threshold_fields = [
            "rules.inaccuracy.lowPersist.belowMmol",
            "rules.sensorAbnormal.lowPersist.belowMmol",
            "rules.sensorFallingOff.durationHours",
            "rules.inaccuracy.max24hMmol",
            "rules.inaccuracy.pairCount",
            "rules.inaccuracy.qualifiedRatio"
        ]
        
        for _ in range(150):
            user = random.choice(users)
            # Pick 1-3 fields that were modified
            modified = random.sample(threshold_fields, k=random.randint(1, 3))
            created_at = now - timedelta(days=random.randint(0, 15), hours=random.randint(0, 23))
            
            log = AuditLog(
                user_id=user.id,
                action="threshold.modify",
                target_type="threshold",
                target_id=str(random.randint(1, 10)),
                status="success",
                event_metadata={
                    "user_id": user.id,
                    "username": user.username,
                    "role": user.role,
                    "distributor_id": user.distributor_id,
                    "distributor_name": user.distributor_name,
                    "modified_fields": modified
                },
                created_at=created_at
            )
            db.add(log)

        await db.commit()
        print("Successfully committed all mock analytics and feedback records to the database!")

if __name__ == "__main__":
    asyncio.run(main())
