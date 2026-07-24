from typing import Optional, Dict, Any
from fastapi import APIRouter, HTTPException, Depends
from app.database import db
from app.models.staff_payroll import Staff, StaffCreate, Attendance, AttendanceToggle, Advance, AdvanceCreate
from app.utils.auth import get_current_user

router = APIRouter(tags=["Staff & Payroll"])

@router.get("/staff")
async def list_staff(user=Depends(get_current_user)):
    return await db.staff.find({}, {"_id": 0}).sort("name", 1).to_list(200)

@router.post("/staff")
async def create_staff(body: StaffCreate, user=Depends(get_current_user)):
    s = Staff(**body.model_dump())
    await db.staff.insert_one(s.model_dump())
    return s.model_dump()

@router.put("/staff/{sid}")
async def update_staff(sid: str, body: StaffCreate, user=Depends(get_current_user)):
    res = await db.staff.update_one({"id": sid}, {"$set": body.model_dump()})
    if res.matched_count == 0:
        raise HTTPException(404, detail="Staff not found")
    return await db.staff.find_one({"id": sid}, {"_id": 0})

@router.delete("/staff/{sid}")
async def delete_staff(sid: str, user=Depends(get_current_user)):
    await db.staff.delete_one({"id": sid})
    return {"ok": True}

@router.get("/attendance")
async def list_attendance(date: Optional[str] = None, month: Optional[str] = None, user=Depends(get_current_user)):
    q: Dict[str, Any] = {}
    if date:
        q["date"] = date
    elif month:
        q["date"] = {"$regex": f"^{month}"}
    return await db.attendance.find(q, {"_id": 0}).to_list(2000)

@router.post("/attendance/toggle")
async def toggle_attendance(body: AttendanceToggle, user=Depends(get_current_user)):
    existing = await db.attendance.find_one({"staff_id": body.staff_id, "date": body.date})
    if existing:
        await db.attendance.update_one(
            {"staff_id": body.staff_id, "date": body.date},
            {"$set": {"present": body.present}},
        )
    else:
        rec = Attendance(staff_id=body.staff_id, date=body.date, present=body.present)
        await db.attendance.insert_one(rec.model_dump())
    return {"ok": True}

@router.get("/advances")
async def list_advances(user=Depends(get_current_user)):
    return await db.advances.find({}, {"_id": 0}).sort("date", -1).to_list(500)

@router.post("/advances")
async def create_advance(body: AdvanceCreate, user=Depends(get_current_user)):
    a = Advance(**body.model_dump())
    await db.advances.insert_one(a.model_dump())
    return a.model_dump()

@router.get("/payroll")
async def payroll(month: str, user=Depends(get_current_user)):
    staff_list = await db.staff.find({}, {"_id": 0}).to_list(500)
    result = []
    invoices = await db.invoices.find({"created_at": {"$regex": f"^{month}"}}, {"_id": 0}).to_list(5000)
    
    jc_map = {}
    for jc in await db.jobcards.find({}, {"_id": 0}).to_list(5000):
        jc_map[jc["id"]] = jc
        
    advances = await db.advances.find({"date": {"$regex": f"^{month}"}}, {"_id": 0}).to_list(5000)
    
    for staff in staff_list:
        commission = 0.0
        for inv in invoices:
            jc = jc_map.get(inv.get("job_card_id"))
            if not jc or jc.get("assigned_mechanic_id") != staff["id"]:
                continue
            for l in inv.get("lines", []):
                if l.get("item_type") == "labor":
                    commission += float(l.get("taxable", 0)) * float(staff.get("commission_pct", 0)) / 100.0
                    
        adv = sum(float(a["amount"]) for a in advances if a["staff_id"] == staff["id"])
        attendance = await db.attendance.find({"staff_id": staff["id"], "date": {"$regex": f"^{month}"}}, {"_id": 0}).to_list(50)
        present_days = sum(1 for a in attendance if a["present"])
        total_days = 30
        base_pro = float(staff["base_salary"]) * (present_days / total_days) if total_days else 0
        net = round(base_pro + commission - adv, 2)
        
        result.append({
            "staff_id": staff["id"],
            "name": staff["name"],
            "role": staff.get("role", ""),
            "base_salary": staff["base_salary"],
            "present_days": present_days,
            "prorated_base": round(base_pro, 2),
            "commission": round(commission, 2),
            "advances": round(adv, 2),
            "net_payable": net,
        })
    return result