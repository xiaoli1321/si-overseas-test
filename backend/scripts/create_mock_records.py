import asyncio
import sys
from pathlib import Path
from datetime import datetime, UTC

# Ensure backend source is in python path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.core.config import get_settings
from src.core.database import AsyncSessionLocal
from src.models.tables import User, Threshold, DetectRecord
from src.rules.engine import run_rules
from src.rules.thresholds import default_thresholds, to_rule_config
from src.integrations.mock_cgm import MockCGMClient, MOCK_DEVICES
from sqlalchemy import select, delete
from fastapi.encoders import jsonable_encoder

async def main():
    settings = get_settings()
    settings.overseas_api_enabled = False
    
    print("Connecting to database...")
    async with AsyncSessionLocal() as db:
        # Find user
        res = await db.execute(select(User).where(User.username == "christest@sibionics.com"))
        user = res.scalar_one_or_none()
        if not user:
            print("Error: User christest@sibionics.com not found!")
            return
        
        # Get active threshold
        res_t = await db.execute(select(Threshold).where(Threshold.user_id == user.id, Threshold.is_active == True))
        threshold = res_t.scalar_one_or_none()
        if not threshold:
            print("Active threshold not found, creating a default one...")
            threshold = Threshold(
                user_id=user.id,
                version=1,
                config_json=default_thresholds(),
                is_active=True,
            )
            db.add(threshold)
            await db.flush()
        
        threshold_config = to_rule_config(threshold.config_json)
        
        # Clean up existing records for these serial numbers to prevent duplicates
        sn_list = list(MOCK_DEVICES.keys())
        await db.execute(delete(DetectRecord).where(DetectRecord.serial_no.in_(sn_list)))
        await db.commit()
        print(f"Cleaned up existing records for {len(sn_list)} mock devices.")
        
        client = MockCGMClient()
        
        created_count = 0
        for sn, mock_dev in MOCK_DEVICES.items():
            print(f"Processing {sn} ({mock_dev['fault']['faultSubtype']})...")
            
            # Fetch mock components
            device = await client.get_device(sn)
            glucose = await client.get_glucose_series(sn)
            alarm = await client.get_latest_alarm(sn)
            
            # Ensure latest_sensor_alert is populated in alarm (for abnormal_time template key)
            if "abnormal_started_at" in alarm:
                alarm["latest_sensor_alert"] = alarm["abnormal_started_at"].isoformat()
            
            # Adjust Persistent Low peak values to satisfy max24hMmol threshold (e.g. 7.0)
            if "Persistent Low" in mock_dev["fault"]["faultSubtype"]:
                for point in glucose["points"]:
                    if point["glucose"] > 7.0:
                        point["glucose"] = 6.5
            
            # Custom params for deviation and application failure
            file_ids = []
            vision_analysis = None
            
            if sn in ("P2251212823BFV10", "P2251212824CGW21"):
                file_ids = ["dev_cgm_1", "dev_bgm_1", "dev_cgm_2", "dev_bgm_2"]
                vision_analysis = {
                    "glucose_readings": [
                        {"value": 4.5, "device_type": "CGM", "unit": "mmol/L", "is_valid": True, "is_reproduced": False},
                        {"value": 12.0, "device_type": "BGM", "unit": "mmol/L", "is_valid": True, "is_reproduced": False},
                        {"value": 4.1, "device_type": "CGM", "unit": "mmol/L", "is_valid": True, "is_reproduced": False},
                        {"value": 11.5, "device_type": "BGM", "unit": "mmol/L", "is_valid": True, "is_reproduced": False}
                    ]
                }
            elif sn == "P2251212813RVK19":
                file_ids = ["app_fail_1", "app_fail_2"]
                vision_analysis = {
                    "is_cgm_device_present": True,
                    "is_reproduced_photo": False,
                    "needle_exposed": True,
                    "adhesive_detached": False,
                    "implanter_damage": False,
                    "scenarios": [
                        {"scenario": "Assembly failed", "matched": False, "confidence": 0.0, "reason": "No match"},
                        {"scenario": "Guiding needle retention", "matched": True, "confidence": 9.0, "reason": "Needle did not retract"},
                        {"scenario": "Exposed Electrodes", "matched": False, "confidence": 0.0, "reason": "No match"},
                        {"scenario": "Adhesive detaching", "matched": False, "confidence": 0.0, "reason": "No match"},
                        {"scenario": "Implanter damage", "matched": False, "confidence": 0.0, "reason": "No match"},
                        {"scenario": "None of the above", "matched": False, "confidence": 0.0, "reason": "No match"}
                    ],
                    "final_scenario": "Guiding needle retention",
                    "final_confidence": 9.0,
                    "score": 9.0,
                }
            elif sn == "P2251212822AEU09":
                file_ids = ["app_fail_1", "app_fail_2"]
                vision_analysis = {
                    "is_cgm_device_present": True,
                    "is_reproduced_photo": False,
                    "needle_exposed": False,
                    "adhesive_detached": False,
                    "implanter_damage": False,
                    "scenarios": [
                        {"scenario": "Assembly failed", "matched": False, "confidence": 0.0, "reason": "No match"},
                        {"scenario": "Guiding needle retention", "matched": False, "confidence": 0.0, "reason": "No match"},
                        {"scenario": "Exposed Electrodes", "matched": False, "confidence": 0.0, "reason": "No match"},
                        {"scenario": "Adhesive detaching", "matched": False, "confidence": 0.0, "reason": "No match"},
                        {"scenario": "Implanter damage", "matched": False, "confidence": 0.0, "reason": "No match"},
                        {"scenario": "None of the above", "matched": True, "confidence": 1.0, "reason": "No failure detected"}
                    ],
                    "final_scenario": "None of the above",
                    "final_confidence": 1.0,
                    "score": 1.0,
                }
            
            # Execute rule engine
            result = run_rules(
                fault_category=device["fault"]["faultCategory"],
                device=device,
                glucose_series=glucose,
                alarm=alarm,
                threshold_config=threshold_config,
                file_ids=file_ids,
                vision_analysis=vision_analysis,
            )
            
            # Construct files metadata for evidence display
            files_metadata = []
            for fid in file_ids:
                files_metadata.append({
                    "id": fid,
                    "filename": f"{fid}.png",
                    "storage_backend": "local",
                    "object_key": f"mock/{fid}.png",
                    "public_url": f"/api/v1/files/{fid}",
                    "mime_type": "image/png",
                    "file_size": 1024,
                })
            
            evidence_data = {
                **(result.evidence or {}),
                "matched_rules": result.matched_rules,
                "files_metadata": files_metadata,
                "file_ids": file_ids,
            }
            
            # Enforce expected verdict and subtypes from mock configurations
            expected_verdict = mock_dev["fault"]["expectedAfterSales"]
            
            # Map subtypes cleanly to config.yaml templates
            expected_subtype = result.fault_subtype
            if device["fault"]["faultCategory"] == "Sensor Abnormal":
                if "Initialization" in mock_dev["fault"]["faultSubtype"]:
                    expected_subtype = "Initialization Abnormal"
                elif "Temporary" in mock_dev["fault"]["faultSubtype"]:
                    if expected_verdict == "Replacement Eligible":
                        expected_subtype = "Low Recovery Possibility"
                    else:
                        expected_subtype = "Waiting Recovery"
            elif expected_verdict == "Not Eligible" and not expected_subtype:
                expected_subtype = "Not Eligible"
            
            # Merge mock device note with rule engine reasons
            final_reasons = []
            note = mock_dev["fault"].get("notes")
            if note:
                final_reasons.append(note)
            final_reasons.extend(result.reasons)
            
            # Create DetectRecord
            record = DetectRecord(
                user_id=user.id,
                serial_no=sn,
                device_type=device["device_type"],
                fault_category=device["fault"]["faultCategory"],
                fault_subtype=expected_subtype,
                status="completed",
                verdict=expected_verdict,
                issue_detected="Issue Detected" if expected_verdict == "Replacement Eligible" else "no issue",
                reasons="\n".join(final_reasons),
                threshold_id=threshold.id,
                threshold_snapshot=jsonable_encoder(threshold.config_json),
                evidence=jsonable_encoder(evidence_data),
                created_by=user.id,
                started_at=datetime.now(UTC),
                completed_at=datetime.now(UTC),
            )
            
            db.add(record)
            created_count += 1
            print(f"  Result: expected={expected_verdict}, saved_subtype={expected_subtype}")
            
        await db.commit()
        print(f"Successfully committed {created_count} mock detection records.")

if __name__ == "__main__":
    asyncio.run(main())
