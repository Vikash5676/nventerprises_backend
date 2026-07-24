from fastapi import APIRouter, Depends
from app.database import db
from app.models.staff_payroll import Expense, ExpenseCreate
from app.utils.auth import get_current_user

router = APIRouter(prefix="/expenses", tags=["Expenses"])

@router.get("")
async def list_expenses(user=Depends(get_current_user)):
    return await db.expenses.find({}, {"_id": 0}).sort("date", -1).to_list(2000)

@router.post("")
async def create_expense(body: ExpenseCreate, user=Depends(get_current_user)):
    e = Expense(**body.model_dump(), source="manual")
    await db.expenses.insert_one(e.model_dump())
    return e.model_dump()

@router.delete("/{eid}")
async def delete_expense(eid: str, user=Depends(get_current_user)):
    await db.expenses.delete_one({"id": eid})
    return {"ok": True}