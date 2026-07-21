from dotenv import load_dotenv
from pathlib import Path

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

import os
import uuid
import logging
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Literal, Dict, Any

import bcrypt
import jwt
from fastapi import FastAPI, APIRouter, HTTPException, Depends, Request, Response, status
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, Field, EmailStr, ConfigDict


# ---------------------------- Config & DB ----------------------------
MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]
JWT_SECRET = os.environ["JWT_SECRET"]
JWT_ALGORITHM = "HS256"
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "owner@garage.in")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin123")

SHOP_INFO = {
    "name": os.environ.get("SHOP_NAME", "Ranchi Motors Workshop"),
    "state": os.environ.get("SHOP_STATE", "Jharkhand"),
    "gstin": os.environ.get("SHOP_GSTIN", "20ABCDE1234F1Z5"),
    "address": os.environ.get("SHOP_ADDRESS", ""),
    "phone": os.environ.get("SHOP_PHONE", ""),
}

client = AsyncIOMotorClient(MONGO_URL)
db = client[DB_NAME]

app = FastAPI(title="Two-Wheeler ERP")
api = APIRouter(prefix="/api")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("erp")


# ---------------------------- Helpers ----------------------------
def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id() -> str:
    return str(uuid.uuid4())


def hash_password(pw: str) -> str:
    return bcrypt.hashpw(pw.encode(), bcrypt.gensalt()).decode()


def verify_password(pw: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(pw.encode(), hashed.encode())
    except Exception:
        return False


def create_access_token(user_id: str, email: str) -> str:
    payload = {
        "sub": user_id,
        "email": email,
        "exp": datetime.now(timezone.utc) + timedelta(hours=12),
        "type": "access",
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


async def get_current_user(request: Request) -> dict:
    token = request.cookies.get("access_token")
    if not token:
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            token = auth[7:]
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")
    user = await db.users.find_one({"id": payload["sub"]}, {"_id": 0, "password_hash": 0})
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user


def strip_mongo(doc: dict) -> dict:
    doc.pop("_id", None)
    return doc


# ---------------------------- Auth Models ----------------------------
class LoginBody(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    id: str
    email: EmailStr
    name: str
    role: str


# ---------------------------- ERP Models ----------------------------
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
    # computed
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
    discount_type: str = ""  # "", "amount", "percent"
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


class Staff(BaseModel):
    id: str = Field(default_factory=new_id)
    name: str
    role: str = "Mechanic"
    phone: str = ""
    base_salary: float = 0.0
    commission_pct: float = 0.0  # percent of labor revenue
    pin: str = ""  # 4-digit PIN for mobile mechanic app
    created_at: str = Field(default_factory=now_iso)


class StaffCreate(BaseModel):
    name: str
    role: str = "Mechanic"
    phone: str = ""
    base_salary: float = 0.0
    commission_pct: float = 0.0
    pin: str = ""


class MechanicLoginBody(BaseModel):
    pin: str


class Attendance(BaseModel):
    id: str = Field(default_factory=new_id)
    staff_id: str
    date: str  # YYYY-MM-DD
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
    source: str = "manual"  # or 'purchase'
    created_at: str = Field(default_factory=now_iso)


class ExpenseCreate(BaseModel):
    category: str
    amount: float
    date: str
    note: str = ""


class ShopSettings(BaseModel):
    name: str = "Ranchi Motors Workshop"
    tagline: str = "Two-Wheeler Repair & Parts"
    logo_base64: str = ""  # data URI or raw base64
    address: str = ""
    phone: str = ""
    gstin: str = ""
    state: str = "Jharkhand"


# ---------------------------- Shop Settings Cache ----------------------------
_SHOP_CACHE: Dict[str, Any] = {}


async def get_shop_state() -> str:
    if "state" in _SHOP_CACHE:
        return _SHOP_CACHE["state"]
    doc = await db.settings.find_one({"id": "shop"}, {"_id": 0})
    if doc:
        _SHOP_CACHE.update(doc)
        return doc.get("state", "Jharkhand")
    return SHOP_INFO["state"]


# ---------------------------- GST Engine ----------------------------
def compute_line_totals(line: dict, customer_state: str, shop_state: str) -> dict:
    qty = float(line.get("qty", 0))
    price = float(line.get("unit_price", 0))
    gst = float(line.get("gst_rate", 18.0))
    taxable = round(qty * price, 2)
    same_state = (customer_state or "").strip().lower() == shop_state.strip().lower()
    if same_state:
        cgst = round(taxable * (gst / 2) / 100, 2)
        sgst = round(taxable * (gst / 2) / 100, 2)
        igst = 0.0
    else:
        cgst = 0.0
        sgst = 0.0
        igst = round(taxable * gst / 100, 2)
    total = round(taxable + cgst + sgst + igst, 2)
    line.update({
        "taxable": taxable,
        "cgst": cgst,
        "sgst": sgst,
        "igst": igst,
        "total": total,
    })
    return line


def compute_invoice_totals(payload: dict, shop_state: str) -> dict:
    customer_state = payload.get("customer_state", "Jharkhand")
    # Base taxable per line (pre-discount) — used to compute discount ratio
    raw_lines = []
    for l in payload["lines"]:
        raw = dict(l)
        raw["_base_taxable"] = round(float(raw.get("qty", 0)) * float(raw.get("unit_price", 0)), 2)
        raw_lines.append(raw)
    base_subtotal = round(sum(r["_base_taxable"] for r in raw_lines), 2)

    # Discount: pre-tax, applied proportionally to each line's taxable
    disc_type = (payload.get("discount_type") or "").lower()  # "" | "amount" | "percent"
    disc_value = float(payload.get("discount_value") or 0)
    if disc_type == "percent":
        discount_total = round(base_subtotal * min(max(disc_value, 0), 100) / 100.0, 2)
    elif disc_type == "amount":
        discount_total = round(min(max(disc_value, 0), base_subtotal), 2)
    else:
        discount_total = 0.0
    ratio = 0.0 if base_subtotal == 0 else discount_total / base_subtotal

    lines = []
    for r in raw_lines:
        eff_price = float(r.get("unit_price", 0)) * (1 - ratio)
        r_out = dict(r)
        r_out["unit_price"] = round(eff_price, 4)
        r_out.pop("_base_taxable", None)
        lines.append(compute_line_totals(r_out, customer_state, shop_state))

    subtotal = round(sum(l["taxable"] for l in lines), 2)
    cgst_total = round(sum(l["cgst"] for l in lines), 2)
    sgst_total = round(sum(l["sgst"] for l in lines), 2)
    igst_total = round(sum(l["igst"] for l in lines), 2)
    grand_total = round(subtotal + cgst_total + sgst_total + igst_total, 2)
    return {
        "lines": lines,
        "gross_subtotal": base_subtotal,
        "discount_type": disc_type,
        "discount_value": disc_value,
        "discount_total": discount_total,
        "subtotal": subtotal,
        "cgst_total": cgst_total,
        "sgst_total": sgst_total,
        "igst_total": igst_total,
        "grand_total": grand_total,
    }


# ---------------------------- Auth Endpoints ----------------------------
@api.post("/auth/login")
async def auth_login(body: LoginBody, response: Response):
    email = body.email.lower().strip()
    user = await db.users.find_one({"email": email})
    if not user or not verify_password(body.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    token = create_access_token(user["id"], user["email"])
    response.set_cookie("access_token", token, httponly=True, samesite="lax", max_age=43200, path="/")
    return {"token": token, "user": {"id": user["id"], "email": user["email"], "name": user["name"], "role": user["role"]}}


@api.post("/auth/logout")
async def auth_logout(response: Response):
    response.delete_cookie("access_token", path="/")
    return {"ok": True}


@api.get("/auth/me")
async def auth_me(user=Depends(get_current_user)):
    return user


@api.get("/shop/info")
async def shop_info():
    doc = await db.settings.find_one({"id": "shop"}, {"_id": 0})
    if not doc:
        # First-time bootstrap from env
        doc = ShopSettings(
            name=SHOP_INFO["name"],
            address=SHOP_INFO["address"],
            phone=SHOP_INFO["phone"],
            gstin=SHOP_INFO["gstin"],
            state=SHOP_INFO["state"],
        ).model_dump()
        doc["id"] = "shop"
        await db.settings.insert_one(doc)
        doc.pop("_id", None)
        _SHOP_CACHE.update(doc)
    return doc


@api.put("/shop/info")
async def update_shop_info(body: ShopSettings, user=Depends(get_current_user)):
    if user.get("role") != "owner":
        raise HTTPException(403, "Only owner can update shop settings")
    data = body.model_dump()
    data["id"] = "shop"
    await db.settings.update_one({"id": "shop"}, {"$set": data}, upsert=True)
    _SHOP_CACHE.clear()
    _SHOP_CACHE.update(data)
    return data


# ---------------------------- Mechanic Mobile Auth (PIN) ----------------------------
@api.post("/mechanic/login")
async def mechanic_login(body: MechanicLoginBody, response: Response):
    pin = (body.pin or "").strip()
    if not pin:
        raise HTTPException(400, "PIN required")
    staff = await db.staff.find_one({"pin": pin}, {"_id": 0})
    if not staff:
        raise HTTPException(401, "Invalid PIN")
    token = jwt.encode(
        {
            "sub": staff["id"],
            "role": "mechanic",
            "type": "mechanic",
            "exp": datetime.now(timezone.utc) + timedelta(hours=12),
        },
        JWT_SECRET,
        algorithm=JWT_ALGORITHM,
    )
    return {"token": token, "staff": staff}


async def get_current_mechanic(request: Request) -> dict:
    auth = request.headers.get("Authorization", "")
    token = auth[7:] if auth.startswith("Bearer ") else request.cookies.get("mechanic_token")
    if not token:
        raise HTTPException(401, "Not authenticated")
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.InvalidTokenError:
        raise HTTPException(401, "Invalid token")
    if payload.get("type") != "mechanic":
        raise HTTPException(403, "Not a mechanic token")
    staff = await db.staff.find_one({"id": payload["sub"]}, {"_id": 0})
    if not staff:
        raise HTTPException(401, "Mechanic not found")
    return staff


@api.get("/mechanic/jobs")
async def mechanic_jobs(mech=Depends(get_current_mechanic)):
    docs = await db.jobcards.find(
        {"assigned_mechanic_id": mech["id"], "status": {"$ne": "invoiced"}}, {"_id": 0}
    ).sort("created_at", -1).to_list(200)
    return {"me": mech, "jobs": docs}


@api.post("/mechanic/jobs/{jc_id}/status")
async def mechanic_update_status(jc_id: str, body: JobStatusUpdate, mech=Depends(get_current_mechanic)):
    jc = await db.jobcards.find_one({"id": jc_id, "assigned_mechanic_id": mech["id"]})
    if not jc:
        raise HTTPException(404, "Job card not assigned to you")
    await db.jobcards.update_one(
        {"id": jc_id},
        {"$set": {"status": body.status, "updated_at": now_iso()}},
    )
    return await db.jobcards.find_one({"id": jc_id}, {"_id": 0})


# ---------------------------- Inventory ----------------------------
@api.get("/inventory")
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


@api.post("/inventory/bulk_import")
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


@api.post("/inventory")
async def create_inventory(body: InventoryUpsert, user=Depends(get_current_user)):
    item = InventoryItem(**body.model_dump())
    await db.inventory.insert_one(item.model_dump())
    return item.model_dump()


@api.put("/inventory/{item_id}")
async def update_inventory(item_id: str, body: InventoryUpsert, user=Depends(get_current_user)):
    res = await db.inventory.update_one({"id": item_id}, {"$set": body.model_dump()})
    if res.matched_count == 0:
        raise HTTPException(404, "Item not found")
    doc = await db.inventory.find_one({"id": item_id}, {"_id": 0})
    return doc


@api.delete("/inventory/{item_id}")
async def delete_inventory(item_id: str, user=Depends(get_current_user)):
    await db.inventory.delete_one({"id": item_id})
    return {"ok": True}


# ---------------------------- Job Cards ----------------------------
@api.get("/jobcards")
async def list_jobcards(user=Depends(get_current_user)):
    docs = await db.jobcards.find({}, {"_id": 0}).sort("created_at", -1).to_list(1000)
    return docs


@api.post("/jobcards")
async def create_jobcard(body: JobCardCreate, user=Depends(get_current_user)):
    data = body.model_dump()
    if data.get("assigned_mechanic_id"):
        mech = await db.staff.find_one({"id": data["assigned_mechanic_id"]}, {"_id": 0})
        if mech:
            data["assigned_mechanic_name"] = mech["name"]
    jc = JobCard(**data)
    await db.jobcards.insert_one(jc.model_dump())
    return jc.model_dump()


@api.put("/jobcards/{jc_id}/status")
async def update_jc_status(jc_id: str, body: JobStatusUpdate, user=Depends(get_current_user)):
    res = await db.jobcards.update_one(
        {"id": jc_id},
        {"$set": {"status": body.status, "updated_at": now_iso()}},
    )
    if res.matched_count == 0:
        raise HTTPException(404, "Job card not found")
    doc = await db.jobcards.find_one({"id": jc_id}, {"_id": 0})
    return doc


@api.delete("/jobcards/{jc_id}")
async def delete_jobcard(jc_id: str, user=Depends(get_current_user)):
    await db.jobcards.delete_one({"id": jc_id})
    return {"ok": True}


# ---------------------------- Invoices / Billing ----------------------------
async def _next_invoice_no() -> str:
    year = datetime.now(timezone.utc).strftime("%y")
    count = await db.invoices.count_documents({})
    return f"INV-{year}-{count + 1:05d}"


@api.get("/invoices")
async def list_invoices(user=Depends(get_current_user)):
    return await db.invoices.find({}, {"_id": 0}).sort("created_at", -1).to_list(1000)


@api.get("/invoices/{inv_id}")
async def get_invoice(inv_id: str, user=Depends(get_current_user)):
    doc = await db.invoices.find_one({"id": inv_id}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Invoice not found")
    return doc


@api.post("/invoices/preview")
async def preview_invoice(body: InvoiceCreate, user=Depends(get_current_user)):
    shop_state = await get_shop_state()
    return compute_invoice_totals(body.model_dump(), shop_state)


@api.post("/invoices")
async def create_invoice(body: InvoiceCreate, user=Depends(get_current_user)):
    payload = body.model_dump()
    shop_state = await get_shop_state()
    totals = compute_invoice_totals(payload, shop_state)
    # decrement stock for parts
    for l in totals["lines"]:
        if l.get("item_id") and l.get("item_type") == "part":
            await db.inventory.update_one({"id": l["item_id"]}, {"$inc": {"stock": -float(l["qty"])}})
    inv = Invoice(
        invoice_no=await _next_invoice_no(),
        customer_name=payload["customer_name"],
        customer_phone=payload.get("customer_phone", ""),
        customer_state=payload.get("customer_state", "Jharkhand"),
        customer_gstin=payload.get("customer_gstin", ""),
        vehicle_number=payload.get("vehicle_number", ""),
        job_card_id=payload.get("job_card_id"),
        lines=[InvoiceLine(**l) for l in totals["lines"]],
        gross_subtotal=totals["gross_subtotal"],
        discount_type=totals["discount_type"],
        discount_value=totals["discount_value"],
        discount_total=totals["discount_total"],
        subtotal=totals["subtotal"],
        cgst_total=totals["cgst_total"],
        sgst_total=totals["sgst_total"],
        igst_total=totals["igst_total"],
        grand_total=totals["grand_total"],
        cash_amount=payload.get("cash_amount", 0.0),
        upi_amount=payload.get("upi_amount", 0.0),
        udhaar_amount=payload.get("udhaar_amount", 0.0),
        notes=payload.get("notes", ""),
    )
    await db.invoices.insert_one(inv.model_dump())
    # If linked to job card, mark invoiced
    if inv.job_card_id:
        await db.jobcards.update_one(
            {"id": inv.job_card_id},
            {"$set": {"status": "invoiced", "invoice_id": inv.id, "updated_at": now_iso()}},
        )
    return inv.model_dump()


# ---------------------------- Suppliers ----------------------------
@api.get("/suppliers")
async def list_suppliers(user=Depends(get_current_user)):
    return await db.suppliers.find({}, {"_id": 0}).sort("name", 1).to_list(500)


@api.post("/suppliers")
async def create_supplier(body: SupplierCreate, user=Depends(get_current_user)):
    s = Supplier(**body.model_dump())
    await db.suppliers.insert_one(s.model_dump())
    return s.model_dump()


@api.delete("/suppliers/{sid}")
async def delete_supplier(sid: str, user=Depends(get_current_user)):
    await db.suppliers.delete_one({"id": sid})
    return {"ok": True}


# ---------------------------- Purchases ----------------------------
@api.get("/purchases")
async def list_purchases(user=Depends(get_current_user)):
    return await db.purchases.find({}, {"_id": 0}).sort("created_at", -1).to_list(500)


@api.post("/purchases")
async def create_purchase(body: PurchaseCreate, user=Depends(get_current_user)):
    supplier = await db.suppliers.find_one({"id": body.supplier_id}, {"_id": 0})
    if not supplier:
        raise HTTPException(404, "Supplier not found")
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
    # increment stock for each item
    for l in body.lines:
        if l.item_id:
            await db.inventory.update_one({"id": l.item_id}, {"$inc": {"stock": float(l.qty)}})
    # supplier payable balance update
    await db.suppliers.update_one({"id": body.supplier_id}, {"$inc": {"payable_balance": balance}})
    # log as expense
    exp = Expense(
        category="Purchase - " + supplier["name"],
        amount=total,
        date=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        note=f"Purchase Invoice {body.invoice_no}",
        source="purchase",
    )
    await db.expenses.insert_one(exp.model_dump())
    return p.model_dump()


# ---------------------------- Staff / Payroll ----------------------------
@api.get("/staff")
async def list_staff(user=Depends(get_current_user)):
    return await db.staff.find({}, {"_id": 0}).sort("name", 1).to_list(200)


@api.post("/staff")
async def create_staff(body: StaffCreate, user=Depends(get_current_user)):
    s = Staff(**body.model_dump())
    await db.staff.insert_one(s.model_dump())
    return s.model_dump()


@api.put("/staff/{sid}")
async def update_staff(sid: str, body: StaffCreate, user=Depends(get_current_user)):
    res = await db.staff.update_one({"id": sid}, {"$set": body.model_dump()})
    if res.matched_count == 0:
        raise HTTPException(404, "Staff not found")
    return await db.staff.find_one({"id": sid}, {"_id": 0})


@api.delete("/staff/{sid}")
async def delete_staff(sid: str, user=Depends(get_current_user)):
    await db.staff.delete_one({"id": sid})
    return {"ok": True}


@api.get("/attendance")
async def list_attendance(date: Optional[str] = None, month: Optional[str] = None, user=Depends(get_current_user)):
    q: Dict[str, Any] = {}
    if date:
        q["date"] = date
    elif month:
        q["date"] = {"$regex": f"^{month}"}
    return await db.attendance.find(q, {"_id": 0}).to_list(2000)


@api.post("/attendance/toggle")
async def toggle_attendance(body: AttendanceToggle, user=Depends(get_current_user)):
    existing = await db.attendance.find_one({"staff_id": body.staff_id, "date": body.date})
    if existing:
        await db.attendance.update_one(
            {"staff_id": body.staff_id, "date": body.date},
            {"$set": {"present": body.present}},
        )
    else:
        rec = Attendance(staff_id=body.staff_id, date=body.date, present=body.present)
        await db.attendance.insert_one(rec.model_dump())
    return {"ok": True}


@api.get("/advances")
async def list_advances(user=Depends(get_current_user)):
    return await db.advances.find({}, {"_id": 0}).sort("date", -1).to_list(500)


@api.post("/advances")
async def create_advance(body: AdvanceCreate, user=Depends(get_current_user)):
    a = Advance(**body.model_dump())
    await db.advances.insert_one(a.model_dump())
    return a.model_dump()


@api.get("/payroll")
async def payroll(month: str, user=Depends(get_current_user)):
    """Returns monthly slip breakdown for each staff.
    month = YYYY-MM"""
    staff_list = await db.staff.find({}, {"_id": 0}).to_list(500)
    result = []
    invoices = await db.invoices.find({"created_at": {"$regex": f"^{month}"}}, {"_id": 0}).to_list(5000)
    # get job cards to link mechanic to labor lines
    jc_map = {}
    for jc in await db.jobcards.find({}, {"_id": 0}).to_list(5000):
        jc_map[jc["id"]] = jc
    advances = await db.advances.find({"date": {"$regex": f"^{month}"}}, {"_id": 0}).to_list(5000)
    for staff in staff_list:
        # commission from labor lines on invoices whose job_card is assigned to this mechanic
        commission = 0.0
        for inv in invoices:
            jc = jc_map.get(inv.get("job_card_id"))
            if not jc:
                continue
            if jc.get("assigned_mechanic_id") != staff["id"]:
                continue
            for l in inv.get("lines", []):
                if l.get("item_type") == "labor":
                    commission += float(l.get("taxable", 0)) * float(staff.get("commission_pct", 0)) / 100.0
        adv = sum(float(a["amount"]) for a in advances if a["staff_id"] == staff["id"])
        # attendance-based salary proration: paid_days / total_days_in_month
        attendance = await db.attendance.find({"staff_id": staff["id"], "date": {"$regex": f"^{month}"}}, {"_id": 0}).to_list(50)
        present_days = sum(1 for a in attendance if a["present"])
        # Total days: 30 default
        total_days = 30
        base_pro = float(staff["base_salary"]) * (present_days / total_days) if total_days else 0
        net = round(base_pro + commission - adv, 2)
        result.append({
            "staff_id": staff["id"],
            "name": staff["name"],
            "role": staff.get("role", ""),
            "base_salary": staff["base_salary"],
            "present_days": present_days,
            "prorated_base": round(base_pro, 2),
            "commission": round(commission, 2),
            "advances": round(adv, 2),
            "net_payable": net,
        })
    return result


# ---------------------------- Expenses ----------------------------
@api.get("/expenses")
async def list_expenses(user=Depends(get_current_user)):
    return await db.expenses.find({}, {"_id": 0}).sort("date", -1).to_list(2000)


@api.post("/expenses")
async def create_expense(body: ExpenseCreate, user=Depends(get_current_user)):
    e = Expense(**body.model_dump(), source="manual")
    await db.expenses.insert_one(e.model_dump())
    return e.model_dump()


@api.delete("/expenses/{eid}")
async def delete_expense(eid: str, user=Depends(get_current_user)):
    await db.expenses.delete_one({"id": eid})
    return {"ok": True}


# ---------------------------- Dashboard ----------------------------
@api.get("/dashboard")
async def dashboard(user=Depends(get_current_user)):
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    start_7d = (datetime.now(timezone.utc) - timedelta(days=6)).strftime("%Y-%m-%d")

    # Single aggregation for 7-day trend (groups invoices by date prefix)
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

    # Today's expenses (single aggregation)
    exp_agg = await db.expenses.aggregate([
        {"$match": {"date": today}},
        {"$group": {"_id": None, "total": {"$sum": "$amount"}}},
    ]).to_list(1)
    exp_today = round(exp_agg[0]["total"], 2) if exp_agg else 0.0

    # Active bikes count + total udhaar (single aggregations)
    active_bikes = await db.jobcards.count_documents({"status": {"$ne": "invoiced"}})

    ud_agg = await db.invoices.aggregate([
        {"$group": {"_id": None, "total": {"$sum": "$udhaar_amount"}}},
    ]).to_list(1)
    udhaar_total = round(ud_agg[0]["total"], 2) if ud_agg else 0.0

    # Active vehicles + recent invoices in parallel
    active_vehicles = await db.jobcards.find(
        {"status": {"$ne": "invoiced"}}, {"_id": 0}
    ).sort("created_at", -1).to_list(50)
    recent = await db.invoices.find({}, {"_id": 0}).sort("created_at", -1).to_list(10)

    # Low stock via $expr filter (single query)
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


# ---------------------------- Customers ----------------------------
@api.get("/customers")
async def list_customers(user=Depends(get_current_user)):
    """Aggregate customers by phone number using a mongo pipeline."""
    # Aggregate invoices by phone
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

    # Union with jobcards
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


@api.get("/customers/{phone}/ledger")
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


# ---------------------------- GST Reports ----------------------------
@api.get("/reports/gstr1")
async def gstr1(month: str, user=Depends(get_current_user)):
    """GSTR-1 outward supply summary. month = YYYY-MM"""
    invoices = await db.invoices.find({"created_at": {"$regex": f"^{month}"}}, {"_id": 0}).to_list(5000)
    rows = []
    total_taxable = 0.0
    total_cgst = 0.0
    total_sgst = 0.0
    total_igst = 0.0
    total = 0.0
    for inv in invoices:
        rows.append({
            "invoice_no": inv["invoice_no"],
            "date": inv["created_at"][:10],
            "customer_name": inv["customer_name"],
            "customer_gstin": inv.get("customer_gstin", ""),
            "customer_state": inv.get("customer_state", ""),
            "taxable": inv["subtotal"],
            "cgst": inv["cgst_total"],
            "sgst": inv["sgst_total"],
            "igst": inv["igst_total"],
            "total": inv["grand_total"],
        })
        total_taxable += inv["subtotal"]
        total_cgst += inv["cgst_total"]
        total_sgst += inv["sgst_total"]
        total_igst += inv["igst_total"]
        total += inv["grand_total"]
    return {
        "rows": rows,
        "totals": {
            "taxable": round(total_taxable, 2),
            "cgst": round(total_cgst, 2),
            "sgst": round(total_sgst, 2),
            "igst": round(total_igst, 2),
            "total": round(total, 2),
        },
    }


@api.get("/reports/gstr3b")
async def gstr3b(month: str, user=Depends(get_current_user)):
    """Simplified GSTR-3B. month = YYYY-MM"""
    invoices = await db.invoices.find({"created_at": {"$regex": f"^{month}"}}, {"_id": 0}).to_list(5000)
    outward_taxable = round(sum(i["subtotal"] for i in invoices), 2)
    outward_cgst = round(sum(i["cgst_total"] for i in invoices), 2)
    outward_sgst = round(sum(i["sgst_total"] for i in invoices), 2)
    outward_igst = round(sum(i["igst_total"] for i in invoices), 2)
    return {
        "month": month,
        "outward_supplies": {
            "taxable": outward_taxable,
            "cgst": outward_cgst,
            "sgst": outward_sgst,
            "igst": outward_igst,
            "total_tax": round(outward_cgst + outward_sgst + outward_igst, 2),
        },
    }


@api.get("/reports/gstr1.json")
async def gstr1_portal_json(month: str, user=Depends(get_current_user)):
    """GSTR-1 in government portal-compatible JSON shape (simplified)."""
    invoices = await db.invoices.find({"created_at": {"$regex": f"^{month}"}}, {"_id": 0}).to_list(5000)
    b2b, b2cs = [], {}
    for inv in invoices:
        if inv.get("customer_gstin"):
            b2b.append({
                "ctin": inv["customer_gstin"],
                "inv": [{
                    "inum": inv["invoice_no"],
                    "idt": inv["created_at"][:10],
                    "val": inv["grand_total"],
                    "pos": inv.get("customer_state", ""),
                    "rchrg": "N",
                    "inv_typ": "R",
                    "itms": [
                        {
                            "num": i + 1,
                            "itm_det": {
                                "txval": l["taxable"],
                                "rt": l["gst_rate"],
                                "camt": l["cgst"],
                                "samt": l["sgst"],
                                "iamt": l["igst"],
                                "csamt": 0,
                            },
                        }
                        for i, l in enumerate(inv["lines"])
                    ],
                }],
            })
        else:
            key = f"{inv.get('customer_state','JH')}-{inv['lines'][0]['gst_rate'] if inv['lines'] else 18}"
            row = b2cs.setdefault(key, {
                "sply_ty": "INTRA" if inv["cgst_total"] > 0 else "INTER",
                "pos": inv.get("customer_state", ""),
                "rt": inv["lines"][0]["gst_rate"] if inv["lines"] else 18,
                "typ": "OE",
                "txval": 0.0,
                "camt": 0.0,
                "samt": 0.0,
                "iamt": 0.0,
                "csamt": 0.0,
            })
            row["txval"] = round(row["txval"] + inv["subtotal"], 2)
            row["camt"] = round(row["camt"] + inv["cgst_total"], 2)
            row["samt"] = round(row["samt"] + inv["sgst_total"], 2)
            row["iamt"] = round(row["iamt"] + inv["igst_total"], 2)
    return {
        "gstin": SHOP_INFO["gstin"],
        "fp": month.replace("-", ""),
        "gt": round(sum(i["grand_total"] for i in invoices), 2),
        "cur_gt": round(sum(i["grand_total"] for i in invoices), 2),
        "b2b": b2b,
        "b2cs": list(b2cs.values()),
    }


# ---------------------------- Startup ----------------------------
@app.on_event("startup")
async def on_startup():
    await db.users.create_index("email", unique=True)
    await db.inventory.create_index("name")
    await db.inventory.create_index("barcode")
    await db.jobcards.create_index("status")
    await db.invoices.create_index("invoice_no", unique=True)

    # Seed admin
    existing = await db.users.find_one({"email": ADMIN_EMAIL})
    if not existing:
        await db.users.insert_one({
            "id": new_id(),
            "email": ADMIN_EMAIL,
            "password_hash": hash_password(ADMIN_PASSWORD),
            "name": "Shop Owner",
            "role": "owner",
            "created_at": now_iso(),
        })
        logger.info(f"Seeded admin user {ADMIN_EMAIL}")
    elif not verify_password(ADMIN_PASSWORD, existing["password_hash"]):
        await db.users.update_one({"email": ADMIN_EMAIL}, {"$set": {"password_hash": hash_password(ADMIN_PASSWORD)}})

    # Backfill PINs for existing staff who don't have one
    pins = ["1001", "1002", "1003", "1004", "1005", "1006"]
    idx = 0
    async for s in db.staff.find({"$or": [{"pin": ""}, {"pin": {"$exists": False}}]}):
        if idx < len(pins):
            await db.staff.update_one({"id": s["id"]}, {"$set": {"pin": pins[idx]}})
            idx += 1

    # Seed data if fresh
    if await db.inventory.count_documents({}) == 0:
        await _seed_demo_data()


async def _seed_demo_data():
    parts = [
        {"name": "Engine Oil 10W-30 (1L)", "item_type": "part", "hsn_sac": "27101980", "stock": 24, "unit_price": 420, "low_stock_threshold": 6, "rack_location": "Rack A, Shelf 1", "gst_rate": 18, "barcode": "8901030100011"},
        {"name": "Brake Pad Set - Splendor", "item_type": "part", "hsn_sac": "87083000", "stock": 12, "unit_price": 380, "low_stock_threshold": 4, "rack_location": "Rack B, Shelf 2", "gst_rate": 28, "barcode": "8901030100022"},
        {"name": "Spark Plug NGK", "item_type": "part", "hsn_sac": "85111000", "stock": 45, "unit_price": 150, "low_stock_threshold": 10, "rack_location": "Rack C, Shelf 1", "gst_rate": 18, "barcode": "8901030100033"},
        {"name": "Clutch Plate - Pulsar 150", "item_type": "part", "hsn_sac": "87089900", "stock": 3, "unit_price": 780, "low_stock_threshold": 5, "rack_location": "Rack B, Shelf 4", "gst_rate": 28, "barcode": "8901030100044"},
        {"name": "Chain & Sprocket Set", "item_type": "part", "hsn_sac": "84839000", "stock": 8, "unit_price": 1250, "low_stock_threshold": 3, "rack_location": "Rack D, Shelf 2", "gst_rate": 18, "barcode": "8901030100055"},
        {"name": "Air Filter Element", "item_type": "part", "hsn_sac": "84213100", "stock": 15, "unit_price": 220, "low_stock_threshold": 5, "rack_location": "Rack A, Shelf 3", "gst_rate": 18, "barcode": "8901030100066"},
        {"name": "Tyre Tube 90/90-17", "item_type": "part", "hsn_sac": "40131020", "stock": 6, "unit_price": 340, "low_stock_threshold": 4, "rack_location": "Rack E, Shelf 1", "gst_rate": 28, "barcode": "8901030100077"},
        {"name": "Battery 5Ah Amaron", "item_type": "part", "hsn_sac": "85071000", "stock": 4, "unit_price": 1650, "low_stock_threshold": 2, "rack_location": "Rack F, Shelf 1", "gst_rate": 28, "barcode": "8901030100088"},
        {"name": "Head Light Bulb 12V/35W", "item_type": "part", "hsn_sac": "85392990", "stock": 22, "unit_price": 95, "low_stock_threshold": 8, "rack_location": "Rack C, Shelf 3", "gst_rate": 18, "barcode": "8901030100099"},
        # Labor / services
        {"name": "General Service", "item_type": "labor", "hsn_sac": "998714", "stock": 0, "unit_price": 450, "low_stock_threshold": 0, "rack_location": "-", "gst_rate": 18},
        {"name": "Engine Overhaul", "item_type": "labor", "hsn_sac": "998714", "stock": 0, "unit_price": 2500, "low_stock_threshold": 0, "rack_location": "-", "gst_rate": 18},
        {"name": "Chain Adjustment", "item_type": "labor", "hsn_sac": "998714", "stock": 0, "unit_price": 100, "low_stock_threshold": 0, "rack_location": "-", "gst_rate": 18},
        {"name": "Wheel Alignment", "item_type": "labor", "hsn_sac": "998714", "stock": 0, "unit_price": 250, "low_stock_threshold": 0, "rack_location": "-", "gst_rate": 18},
        {"name": "Puncture Repair", "item_type": "labor", "hsn_sac": "998714", "stock": 0, "unit_price": 80, "low_stock_threshold": 0, "rack_location": "-", "gst_rate": 18},
    ]
    for p in parts:
        item = InventoryItem(**p)
        await db.inventory.insert_one(item.model_dump())

    # Staff
    staff_seed = [
        {"name": "Ramesh Kumar", "role": "Head Mechanic", "phone": "9876543210", "base_salary": 22000, "commission_pct": 40, "pin": "1001"},
        {"name": "Suresh Yadav", "role": "Mechanic", "phone": "9876543211", "base_salary": 15000, "commission_pct": 30, "pin": "1002"},
        {"name": "Prakash Singh", "role": "Helper", "phone": "9876543212", "base_salary": 10000, "commission_pct": 15, "pin": "1003"},
        {"name": "Vikas Mahto", "role": "Mechanic", "phone": "9876543213", "base_salary": 16000, "commission_pct": 30, "pin": "1004"},
    ]
    inserted_staff = []
    for s in staff_seed:
        obj = Staff(**s)
        await db.staff.insert_one(obj.model_dump())
        inserted_staff.append(obj)

    # Suppliers
    suppliers = [
        {"name": "Bharat Auto Parts", "gstin": "20AABCB1234C1Z2", "phone": "9433223344", "address": "Ratu Road, Ranchi"},
        {"name": "MotoWorld Distributors", "gstin": "20MOTO4567D1Z9", "phone": "9433221100", "address": "Doranda, Ranchi"},
    ]
    for s in suppliers:
        obj = Supplier(**s)
        await db.suppliers.insert_one(obj.model_dump())

    # Job Cards
    jcs = [
        {"vehicle_number": "JH01AB1234", "model_name": "Hero Splendor Plus", "customer_name": "Rajesh Kumar", "phone": "9812345671", "fuel_level": 60, "complaints": "Engine noise + oil change", "status": "in_progress", "assigned_mechanic_id": inserted_staff[0].id, "assigned_mechanic_name": inserted_staff[0].name},
        {"vehicle_number": "JH05CD9988", "model_name": "Bajaj Pulsar 150", "customer_name": "Amit Sharma", "phone": "9812345672", "fuel_level": 40, "complaints": "Clutch slip", "status": "checked_in", "assigned_mechanic_id": inserted_staff[1].id, "assigned_mechanic_name": inserted_staff[1].name},
        {"vehicle_number": "JH02EF4455", "model_name": "TVS Apache RTR", "customer_name": "Priya Devi", "phone": "9812345673", "fuel_level": 20, "complaints": "Puncture + brake service", "status": "ready", "assigned_mechanic_id": inserted_staff[3].id, "assigned_mechanic_name": inserted_staff[3].name},
    ]
    for jc in jcs:
        obj = JobCard(**jc)
        await db.jobcards.insert_one(obj.model_dump())

    # Expenses seed
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    for e in [
        {"category": "Electricity", "amount": 320, "date": today, "note": "Daily estimate"},
        {"category": "Tea/Snacks", "amount": 180, "date": today, "note": "Staff"},
    ]:
        obj = Expense(**e, source="manual")
        await db.expenses.insert_one(obj.model_dump())

    logger.info("Demo data seeded")


@app.on_event("shutdown")
async def on_shutdown():
    client.close()


# ---------------------------- Mount ----------------------------
app.include_router(api)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)
