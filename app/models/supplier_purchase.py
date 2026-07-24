from typing import List, Optional
from pydantic import BaseModel, Field
from app.models.erp import new_id, now_iso

class Supplier(BaseModel):
    id: str = Field(default_factory=new_id)
    name: str
    gstin: str = ""
    phone: str = ""
    address: str = ""
    payable_balance: float = 0.0
    created_at: str = Field(default_factory=now_iso)

class SupplierCreate(BaseModel):
    name: str
    gstin: str = ""
    phone: str = ""
    address: str = ""

class SupplierUpdate(BaseModel):
    name: Optional[str] = None
    gstin: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None

class PurchaseLine(BaseModel):
    item_id: Optional[str] = None
    name: str
    hsn_sac: str = ""
    qty: float = 1.0
    unit_cost: float = 0.0

class PurchaseCreate(BaseModel):
    supplier_id: str
    invoice_no: str = ""
    lines: List[PurchaseLine]
    paid_amount: float = 0.0
    notes: str = ""

class Purchase(BaseModel):
    id: str = Field(default_factory=new_id)
    supplier_id: str
    supplier_name: str
    invoice_no: str = ""
    lines: List[PurchaseLine]
    total: float
    paid_amount: float
    balance: float
    notes: str = ""
    created_at: str = Field(default_factory=now_iso)