from typing import List, Dict, Any
from fastapi import APIRouter, Depends
from app.database import db
from app.utils.auth import get_current_user

router = APIRouter(prefix="/customers", tags=["Customers"])

@router.get("")
async def list_customers(user=Depends(get_current_user)):
    inv_pipeline = [
        {"$group": {
            "_id": {"$ifNull": ["$customer_phone", ""]},
            "name": {"$last": "$customer_name"},
            "invoice_count": {"$sum": 1},
            "total_billed": {"$sum": "$grand_total"},
            "total_udhaar": {"$sum": "$udhaar_amount"},
            "last_visit": {"$max": "$created_at"},
            "vehicles": {"$addToSet": "$vehicle_number"},
        }},
    ]
    invs = {d["_id"]: d async for d in db.invoices.aggregate(inv_pipeline)}

    jc_pipeline = [
        {"$group": {
            "_id": {"$ifNull": ["$phone", ""]},
            "name": {"$last": "$customer_name"},
            "last_visit": {"$max": "$created_at"},
            "vehicles": {"$addToSet": "$vehicle_number"},
        }},
    ]
    jcs = {d["_id"]: d async for d in db.jobcards.aggregate(jc_pipeline)}

    result: List[Dict[str, Any]] = []
    all_keys = set(invs.keys()) | set(jcs.keys())
    for key in all_keys:
        inv = invs.get(key, {})
        jc = jcs.get(key, {})
        vehicles = sorted({v for v in (inv.get("vehicles", []) + jc.get("vehicles", [])) if v})
        result.append({
            "phone": key,
            "name": inv.get("name") or jc.get("name") or "",
            "vehicle_numbers": vehicles,
            "invoice_count": inv.get("invoice_count", 0),
            "total_billed": round(inv.get("total_billed", 0), 2),
            "total_udhaar": round(inv.get("total_udhaar", 0), 2),
            "last_visit": inv.get("last_visit") or jc.get("last_visit") or "",
        })
    result.sort(key=lambda x: x["total_udhaar"], reverse=True)
    return result

@router.get("/{phone}/ledger")
async def customer_ledger(phone: str, user=Depends(get_current_user)):
    invs = await db.invoices.find({"customer_phone": phone}, {"_id": 0}).sort("created_at", -1).to_list(500)
    jcs = await db.jobcards.find({"phone": phone}, {"_id": 0}).sort("created_at", -1).to_list(500)
    total_udhaar = round(sum(i.get("udhaar_amount", 0) for i in invs), 2)
    total_billed = round(sum(i.get("grand_total", 0) for i in invs), 2)
    return {
        "phone": phone,
        "invoices": invs,
        "job_cards": jcs,
        "total_billed": total_billed,
        "total_udhaar": total_udhaar,
    }