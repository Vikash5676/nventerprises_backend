import jwt
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, HTTPException, Depends, Response
from app.database import db
from app.config import settings
from app.models.auth import MechanicLoginBody
from app.models.erp import JobStatusUpdate
from app.models.erp import now_iso
from app.utils.auth import get_current_mechanic

router = APIRouter(prefix="/mechanic", tags=["Mechanic Mobile"])

@router.post("/login")
async def mechanic_login(body: MechanicLoginBody, response: Response):
    pin = (body.pin or "").strip()
    if not pin:
        raise HTTPException(400, detail="PIN required")
    staff = await db.staff.find_one({"pin": pin}, {"_id": 0})
    if not staff:
        raise HTTPException(401, detail="Invalid PIN")
    token = jwt.encode(
        {
            "sub": staff["id"],
            "role": "mechanic",
            "type": "mechanic",
            "exp": datetime.now(timezone.utc) + timedelta(hours=12),
        },
        settings.JWT_SECRET,
        algorithm=settings.JWT_ALGORITHM,
    )
    return {"token": token, "staff": staff}

@router.get("/jobs")
async def mechanic_jobs(mech=Depends(get_current_mechanic)):
    docs = await db.jobcards.find(
        {"assigned_mechanic_id": mech["id"], "status": {"$ne": "invoiced"}}, {"_id": 0}
    ).sort("created_at", -1).to_list(200)
    return {"me": mech, "jobs": docs}

@router.post("/jobs/{jc_id}/status")
async def mechanic_update_status(jc_id: str, body: JobStatusUpdate, mech=Depends(get_current_mechanic)):
    jc = await db.jobcards.find_one({"id": jc_id, "assigned_mechanic_id": mech["id"]})
    if not jc:
        raise HTTPException(404, detail="Job card not assigned to you")
    await db.jobcards.update_one(
        {"id": jc_id},
        {"$set": {"status": body.status, "updated_at": now_iso()}},
    )
    return await db.jobcards.find_one({"id": jc_id}, {"_id": 0})