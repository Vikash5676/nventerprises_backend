import uuid
from datetime import datetime, timezone
from typing import List, Optional, Literal
from pydantic import BaseModel, Field

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def new_id() -> str:
    return str(uuid.uuid4())

class InventoryItem(BaseModel):
    id: str = Field(default_factory=new_id)
    name: str
    item_type: Literal["part", "labor"] = "part"
    hsn_sac: str = ""
    stock: float = 0.0
    unit_price: float = 0.0
    low_stock_threshold: float = 5.0
    rack_location: str = ""
    gst_rate: float = 18.0
    barcode: Optional[str] = None
    created_at: str = Field(default_factory=now_iso)

class InventoryUpsert(BaseModel):
    name: str
    item_type: Literal["part", "labor"] = "part"
    hsn_sac: str = ""
    stock: float = 0.0
    unit_price: float = 0.0
    low_stock_threshold: float = 5.0
    rack_location: str = ""
    gst_rate: float = 18.0
    barcode: Optional[str] = None

class BulkImportRow(BaseModel):
    name: str
    item_type: Literal["part", "labor"] = "part"
    hsn_sac: str = ""
    stock: float = 0.0
    unit_price: float = 0.0
    low_stock_threshold: float = 5.0
    rack_location: str = ""
    gst_rate: float = 18.0
    barcode: Optional[str] = None

class BulkImportBody(BaseModel):
    rows: List[BulkImportRow]
    upsert_by_barcode: bool = True

class JobCard(BaseModel):
    id: str = Field(default_factory=new_id)
    vehicle_number: str
    model_name: str
    customer_name: str
    phone: str
    fuel_level: int = 50
    scratch_notes: str = ""
    scratch_map: List[str] = []
    assigned_mechanic_id: Optional[str] = None
    assigned_mechanic_name: Optional[str] = None
    complaints: str = ""
    status: Literal["checked_in", "in_progress", "ready", "invoiced"] = "checked_in"
    created_at: str = Field(default_factory=now_iso)
    updated_at: str = Field(default_factory=now_iso)
    invoice_id: Optional[str] = None

class JobCardCreate(BaseModel):
    vehicle_number: str
    model_name: str
    customer_name: str
    phone: str
    fuel_level: int = 50
    scratch_notes: str = ""
    scratch_map: List[str] = []
    assigned_mechanic_id: Optional[str] = None
    complaints: str = ""

class JobStatusUpdate(BaseModel):
    status: Literal["checked_in", "in_progress", "ready", "invoiced"]

class InvoiceLine(BaseModel):
    item_id: Optional[str] = None
    name: str
    item_type: Literal["part", "labor"] = "part"
    hsn_sac: str = ""
    qty: float = 1.0
    unit_price: float = 0.0
    gst_rate: float = 18.0
    taxable: float = 0.0
    cgst: float = 0.0
    sgst: float = 0.0
    igst: float = 0.0
    total: float = 0.0

class InvoiceCreate(BaseModel):
    customer_name: str
    customer_phone: str = ""
    customer_state: str = "Jharkhand"
    customer_gstin: str = ""
    vehicle_number: str = ""
    job_card_id: Optional[str] = None
    lines: List[InvoiceLine]
    cash_amount: float = 0.0
    upi_amount: float = 0.0
    udhaar_amount: float = 0.0
    discount_type: str = ""
    discount_value: float = 0.0
    notes: str = ""

class Invoice(BaseModel):
    id: str = Field(default_factory=new_id)
    invoice_no: str
    customer_name: str
    customer_phone: str = ""
    customer_state: str = "Jharkhand"
    customer_gstin: str = ""
    vehicle_number: str = ""
    job_card_id: Optional[str] = None
    lines: List[InvoiceLine]
    gross_subtotal: float = 0.0
    discount_type: str = ""
    discount_value: float = 0.0
    discount_total: float = 0.0
    subtotal: float
    cgst_total: float
    sgst_total: float
    igst_total: float
    grand_total: float
    cash_amount: float = 0.0
    upi_amount: float = 0.0
    udhaar_amount: float = 0.0
    notes: str = ""
    created_at: str = Field(default_factory=now_iso)

class ShopSettings(BaseModel):
    name: str = "Ranchi Motors Workshop"
    tagline: str = "Two-Wheeler Repair & Parts"
    logo_base64: str = ""
    address: str = ""
    phone: str = ""
    gstin: str = ""
    state: str = "Jharkhand"