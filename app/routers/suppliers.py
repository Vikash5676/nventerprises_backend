from fastapi import APIRouter, Depends
from app.database import db
from app.models.supplier_purchase import Supplier, SupplierCreate, SupplierUpdate
from app.utils.auth import get_current_user

router = APIRouter(prefix="/suppliers", tags=["Suppliers"])

@router.get("")
async def list_suppliers(user=Depends(get_current_user)):
    return await db.suppliers.find({}, {"_id": 0}).sort("name", 1).to_list(500)

@router.post("")
async def create_supplier(body: SupplierCreate, user=Depends(get_current_user)):
    s = Supplier(**body.model_dump())
    await db.suppliers.insert_one(s.model_dump())
    return s.model_dump()

@router.put("/{sid}")
async def update_supplier(sid: str, body: SupplierUpdate, user=Depends(get_current_user)):
    # Exclude fields that weren't explicitly passed in the payload
    update_data = body.model_dump(exclude_unset=True)
    
    if not update_data:
        raise HTTPException(status_code=400, detail="No fields provided to update")

    res = await db.suppliers.update_one({"id": sid}, {"$set": update_data})

    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Supplier not found")

    return await db.suppliers.find_one({"id": sid}, {"_id": 0})

@router.delete("/{sid}")
async def delete_supplier(sid: str, user=Depends(get_current_user)):
    await db.suppliers.delete_one({"id": sid})
    return {"ok": True}