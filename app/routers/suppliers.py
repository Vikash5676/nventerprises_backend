from fastapi import APIRouter, Depends
from app.database import db
from app.models.supplier_purchase import Supplier, SupplierCreate
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

@router.delete("/{sid}")
async def delete_supplier(sid: str, user=Depends(get_current_user)):
    await db.suppliers.delete_one({"id": sid})
    return {"ok": True}