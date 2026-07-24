import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from fastapi import FastAPI, APIRouter
from starlette.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import db, client
from app.models.erp import InventoryItem, JobCard, new_id, now_iso
from app.models.supplier_purchase import Supplier
from app.models.staff_payroll import Staff, Expense
from app.utils.auth import hash_password, verify_password

from app.routers import (
    auth, shop, mechanic, inventory, jobcards,
    invoices, suppliers, purchases, staff, expenses,
    dashboard, customers, reports
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("erp")

async def seed_demo_data():
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
        {"name": "General Service", "item_type": "labor", "hsn_sac": "998714", "stock": 0, "unit_price": 450, "low_stock_threshold": 0, "rack_location": "-", "gst_rate": 18},
        {"name": "Engine Overhaul", "item_type": "labor", "hsn_sac": "998714", "stock": 0, "unit_price": 2500, "low_stock_threshold": 0, "rack_location": "-", "gst_rate": 18},
        {"name": "Chain Adjustment", "item_type": "labor", "hsn_sac": "998714", "stock": 0, "unit_price": 100, "low_stock_threshold": 0, "rack_location": "-", "gst_rate": 18},
        {"name": "Wheel Alignment", "item_type": "labor", "hsn_sac": "998714", "stock": 0, "unit_price": 250, "low_stock_threshold": 0, "rack_location": "-", "gst_rate": 18},
        {"name": "Puncture Repair", "item_type": "labor", "hsn_sac": "998714", "stock": 0, "unit_price": 80, "low_stock_threshold": 0, "rack_location": "-", "gst_rate": 18},
    ]
    for p in parts:
        item = InventoryItem(**p)
        await db.inventory.insert_one(item.model_dump())

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

    suppliers = [
        {"name": "Bharat Auto Parts", "gstin": "20AABCB1234C1Z2", "phone": "9433223344", "address": "Ratu Road, Ranchi"},
        {"name": "MotoWorld Distributors", "gstin": "20MOTO4567D1Z9", "phone": "9433221100", "address": "Doranda, Ranchi"},
    ]
    for s in suppliers:
        obj = Supplier(**s)
        await db.suppliers.insert_one(obj.model_dump())

    jcs = [
        {"vehicle_number": "JH01AB1234", "model_name": "Hero Splendor Plus", "customer_name": "Rajesh Kumar", "phone": "9812345671", "fuel_level": 60, "complaints": "Engine noise + oil change", "status": "in_progress", "assigned_mechanic_id": inserted_staff[0].id, "assigned_mechanic_name": inserted_staff[0].name},
        {"vehicle_number": "JH05CD9988", "model_name": "Bajaj Pulsar 150", "customer_name": "Amit Sharma", "phone": "9812345672", "fuel_level": 40, "complaints": "Clutch slip", "status": "checked_in", "assigned_mechanic_id": inserted_staff[1].id, "assigned_mechanic_name": inserted_staff[1].name},
        {"vehicle_number": "JH02EF4455", "model_name": "TVS Apache RTR", "customer_name": "Priya Devi", "phone": "9812345673", "fuel_level": 20, "complaints": "Puncture + brake service", "status": "ready", "assigned_mechanic_id": inserted_staff[3].id, "assigned_mechanic_name": inserted_staff[3].name},
    ]
    for jc in jcs:
        obj = JobCard(**jc)
        await db.jobcards.insert_one(obj.model_dump())

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    for e in [
        {"category": "Electricity", "amount": 320, "date": today, "note": "Daily estimate"},
        {"category": "Tea/Snacks", "amount": 180, "date": today, "note": "Staff"},
    ]:
        obj = Expense(**e, source="manual")
        await db.expenses.insert_one(obj.model_dump())

    logger.info("Demo data seeded")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup tasks
    await db.users.create_index("email", unique=True)
    await db.inventory.create_index("name")
    await db.inventory.create_index("barcode")
    await db.jobcards.create_index("status")
    await db.invoices.create_index("invoice_no", unique=True)

    existing = await db.users.find_one({"email": settings.ADMIN_EMAIL})
    if not existing:
        await db.users.insert_one({
            "id": new_id(),
            "email": settings.ADMIN_EMAIL,
            "password_hash": hash_password(settings.ADMIN_PASSWORD),
            "name": "Shop Owner",
            "role": "owner",
            "created_at": now_iso(),
        })
        logger.info(f"Seeded admin user {settings.ADMIN_EMAIL}")
    elif not verify_password(settings.ADMIN_PASSWORD, existing["password_hash"]):
        await db.users.update_one({"email": settings.ADMIN_EMAIL}, {"$set": {"password_hash": hash_password(settings.ADMIN_PASSWORD)}})

    pins = ["1001", "1002", "1003", "1004", "1005", "1006"]
    idx = 0
    async for s in db.staff.find({"$or": [{"pin": ""}, {"pin": {"$exists": False}}]}):
        if idx < len(pins):
            await db.staff.update_one({"id": s["id"]}, {"$set": {"pin": pins[idx]}})
            idx += 1

    if await db.inventory.count_documents({}) == 0:
        await seed_demo_data()
        
    yield
    
    # Shutdown tasks
    client.close()

app = FastAPI(title="Two-Wheeler ERP", lifespan=lifespan)
api = APIRouter(prefix="/api")

# Attach sub-routers to main API router
api.include_router(auth.router)
api.include_router(shop.router)
api.include_router(mechanic.router)
api.include_router(inventory.router)
api.include_router(jobcards.router)
api.include_router(invoices.router)
api.include_router(suppliers.router)
api.include_router(purchases.router)
api.include_router(staff.router)
api.include_router(expenses.router)
api.include_router(dashboard.router)
api.include_router(customers.router)
api.include_router(reports.router)

app.include_router(api)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=settings.CORS_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)