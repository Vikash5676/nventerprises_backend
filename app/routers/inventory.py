from typing import Optional, Dict, Any
from fastapi import APIRouter, HTTPException, Depends
from app.database import db
from app.models.erp import InventoryItem, InventoryUpsert, BulkImportBody
from app.utils.auth import get_current_user

router = APIRouter(prefix="/inventory", tags=["Inventory"])

@router.get("")
async def list_inventory(q: Optional[str] = None, user=Depends(get_current_user)):
    query: Dict[str, Any] = {}
    if q:
        query = {"$or": [
            {"name": {"$regex": q, "$options": "i"}},
            {"barcode": q},
            {"hsn_sac": {"$regex": q, "$options": "i"}},
        ]}
    docs = await db.inventory.find(query, {"_id": 0}).sort("name", 1).to_list(2000)
    return docs

@router.post("/bulk_import")
async def inventory_bulk_import(body: BulkImportBody, user=Depends(get_current_user)):
    created, updated = 0, 0
    for r in body.rows:
        existing = None
        if body.upsert_by_barcode and r.barcode:
            existing = await db.inventory.find_one({"barcode": r.barcode})
        if not existing:
            existing = await db.inventory.find_one({"name": r.name})
        if existing:
            await db.inventory.update_one({"id": existing["id"]}, {"$set": r.model_dump()})
            updated += 1
        else:
            item = InventoryItem(**r.model_dump())
            await db.inventory.insert_one(item.model_dump())
            created += 1
    return {"created": created, "updated": updated}

@router.post("")
async def create_inventory(body: InventoryUpsert, user=Depends(get_current_user)):
    item = InventoryItem(**body.model_dump())
    await db.inventory.insert_one(item.model_dump())
    return item.model_dump()

@router.put("/{item_id}")
async def update_inventory(item_id: str, body: InventoryUpsert, user=Depends(get_current_user)):
    res = await db.inventory.update_one({"id": item_id}, {"$set": body.model_dump()})
    if res.matched_count == 0:
        raise HTTPException(404, detail="Item not found")
    doc = await db.inventory.find_one({"id": item_id}, {"_id": 0})
    return doc

@router.delete("/{item_id}")
async def delete_inventory(item_id: str, user=Depends(get_current_user)):
    await db.inventory.delete_one({"id": item_id})
    return {"ok": True}