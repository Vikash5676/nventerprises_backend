from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Depends
from app.database import db
from app.models.supplier_purchase import Purchase, PurchaseCreate
from app.models.staff_payroll import Expense
from app.utils.auth import get_current_user

router = APIRouter(prefix="/purchases", tags=["Purchases"])

@router.get("")
async def list_purchases(user=Depends(get_current_user)):
    return await db.purchases.find({}, {"_id": 0}).sort("created_at", -1).to_list(500)

@router.post("")
async def create_purchase(body: PurchaseCreate, user=Depends(get_current_user)):
    supplier = await db.suppliers.find_one({"id": body.supplier_id}, {"_id": 0})
    if not supplier:
        raise HTTPException(404, detail="Supplier not found")
    
    total = round(sum(l.qty * l.unit_cost for l in body.lines), 2)
    balance = round(total - body.paid_amount, 2)
    p = Purchase(
        supplier_id=body.supplier_id,
        supplier_name=supplier["name"],
        invoice_no=body.invoice_no,
        lines=body.lines,
        total=total,
        paid_amount=body.paid_amount,
        balance=balance,
        notes=body.notes,
    )
    await db.purchases.insert_one(p.model_dump())
    
    for l in body.lines:
        if l.item_id:
            await db.inventory.update_one({"id": l.item_id}, {"$inc": {"stock": float(l.qty)}})
            
    await db.suppliers.update_one({"id": body.supplier_id}, {"$inc": {"payable_balance": balance}})
    
    exp = Expense(
        category="Purchase - " + supplier["name"],
        amount=total,
        date=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        note=f"Purchase Invoice {body.invoice_no}",
        source="purchase",
    )
    await db.expenses.insert_one(exp.model_dump())
    return p.model_dump()