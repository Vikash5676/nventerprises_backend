from fastapi import APIRouter, HTTPException, Depends
from app.database import db
from app.models.erp import JobCard, JobCardCreate, JobStatusUpdate, now_iso
from app.utils.auth import get_current_user

router = APIRouter(prefix="/jobcards", tags=["Job Cards"])

@router.get("")
async def list_jobcards(user=Depends(get_current_user)):
    docs = await db.jobcards.find({}, {"_id": 0}).sort("created_at", -1).to_list(1000)
    return docs

@router.post("")
async def create_jobcard(body: JobCardCreate, user=Depends(get_current_user)):
    data = body.model_dump()
    if data.get("assigned_mechanic_id"):
        mech = await db.staff.find_one({"id": data["assigned_mechanic_id"]}, {"_id": 0})
        if mech:
            data["assigned_mechanic_name"] = mech["name"]
    jc = JobCard(**data)
    await db.jobcards.insert_one(jc.model_dump())
    return jc.model_dump()

@router.put("/{jc_id}/status")
async def update_jc_status(jc_id: str, body: JobStatusUpdate, user=Depends(get_current_user)):
    res = await db.jobcards.update_one(
        {"id": jc_id},
        {"$set": {"status": body.status, "updated_at": now_iso()}},
    )
    if res.matched_count == 0:
        raise HTTPException(404, detail="Job card not found")
    doc = await db.jobcards.find_one({"id": jc_id}, {"_id": 0})
    return doc

@router.delete("/{jc_id}")
async def delete_jobcard(jc_id: str, user=Depends(get_current_user)):
    await db.jobcards.delete_one({"id": jc_id})
    return {"ok": True}