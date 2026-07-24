from pydantic import BaseModel, Field
from app.models.erp import new_id, now_iso

class Staff(BaseModel):
    id: str = Field(default_factory=new_id)
    name: str
    role: str = "Mechanic"
    phone: str = ""
    base_salary: float = 0.0
    commission_pct: float = 0.0
    pin: str = ""
    created_at: str = Field(default_factory=now_iso)

class StaffCreate(BaseModel):
    name: str
    role: str = "Mechanic"
    phone: str = ""
    base_salary: float = 0.0
    commission_pct: float = 0.0
    pin: str = ""

class Attendance(BaseModel):
    id: str = Field(default_factory=new_id)
    staff_id: str
    date: str
    present: bool = True

class AttendanceToggle(BaseModel):
    staff_id: str
    date: str
    present: bool

class Advance(BaseModel):
    id: str = Field(default_factory=new_id)
    staff_id: str
    amount: float
    date: str
    note: str = ""

class AdvanceCreate(BaseModel):
    staff_id: str
    amount: float
    date: str
    note: str = ""

class Expense(BaseModel):
    id: str = Field(default_factory=new_id)
    category: str
    amount: float
    date: str
    note: str = ""
    source: str = "manual"
    created_at: str = Field(default_factory=now_iso)

class ExpenseCreate(BaseModel):
    category: str
    amount: float
    date: str
    note: str = ""