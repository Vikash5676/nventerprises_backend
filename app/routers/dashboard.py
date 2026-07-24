from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends
from app.database import db
from app.utils.auth import get_current_user

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])

@router.get("")
async def dashboard(user=Depends(get_current_user)):
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    start_7d = (datetime.now(timezone.utc) - timedelta(days=6)).strftime("%Y-%m-%d")

    trend_pipeline = [
        {"$match": {"created_at": {"$gte": start_7d}}},
        {"$group": {
            "_id": {"$substr": ["$created_at", 0, 10]},
            "sales": {"$sum": "$grand_total"},
            "count": {"$sum": 1},
        }},
    ]
    trend_docs = {d["_id"]: d async for d in db.invoices.aggregate(trend_pipeline)}

    trend = []
    for i in range(6, -1, -1):
        dt = datetime.now(timezone.utc) - timedelta(days=i)
        d = dt.strftime("%Y-%m-%d")
        rec = trend_docs.get(d, {"sales": 0, "count": 0})
        trend.append({
            "date": d,
            "label": dt.strftime("%a"),
            "sales": round(rec["sales"], 2),
            "count": rec["count"],
        })

    sales_today = next((t["sales"] for t in trend if t["date"] == today), 0.0)

    exp_agg = await db.expenses.aggregate([
        {"$match": {"date": today}},
        {"$group": {"_id": None, "total": {"$sum": "$amount"}}},
    ]).to_list(1)
    exp_today = round(exp_agg[0]["total"], 2) if exp_agg else 0.0

    active_bikes = await db.jobcards.count_documents({"status": {"$ne": "invoiced"}})

    ud_agg = await db.invoices.aggregate([
        {"$group": {"_id": None, "total": {"$sum": "$udhaar_amount"}}},
    ]).to_list(1)
    udhaar_total = round(ud_agg[0]["total"], 2) if ud_agg else 0.0

    active_vehicles = await db.jobcards.find(
        {"status": {"$ne": "invoiced"}}, {"_id": 0}
    ).sort("created_at", -1).to_list(50)
    
    recent = await db.invoices.find({}, {"_id": 0}).sort("created_at", -1).to_list(10)

    low_stock = await db.inventory.find(
        {"item_type": "part", "$expr": {"$lte": ["$stock", "$low_stock_threshold"]}},
        {"_id": 0},
    ).to_list(200)

    return {
        "sales_today": round(sales_today, 2),
        "expenses_today": exp_today,
        "active_bikes": active_bikes,
        "pending_udhaar": udhaar_total,
        "active_vehicles": active_vehicles,
        "recent_invoices": recent,
        "sales_trend": trend,
        "low_stock": low_stock,
    }