from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Depends
from app.database import db
from app.models.erp import Invoice, InvoiceCreate, InvoiceLine, now_iso
from app.utils.auth import get_current_user
from app.utils.gst import get_shop_state, compute_invoice_totals

router = APIRouter(prefix="/invoices", tags=["Invoices"])

async def _next_invoice_no() -> str:
    year = datetime.now(timezone.utc).strftime("%y")
    count = await db.invoices.count_documents({})
    return f"INV-{year}-{count + 1:05d}"

@router.get("")
async def list_invoices(user=Depends(get_current_user)):
    return await db.invoices.find({}, {"_id": 0}).sort("created_at", -1).to_list(1000)

@router.get("/{inv_id}")
async def get_invoice(inv_id: str, user=Depends(get_current_user)):
    doc = await db.invoices.find_one({"id": inv_id}, {"_id": 0})
    if not doc:
        raise HTTPException(404, detail="Invoice not found")
    return doc

@router.post("/preview")
async def preview_invoice(body: InvoiceCreate, user=Depends(get_current_user)):
    shop_state = await get_shop_state()
    return compute_invoice_totals(body.model_dump(), shop_state)

@router.post("")
async def create_invoice(body: InvoiceCreate, user=Depends(get_current_user)):
    payload = body.model_dump()
    shop_state = await get_shop_state()
    totals = compute_invoice_totals(payload, shop_state)
    
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
    
    if inv.job_card_id:
        await db.jobcards.update_one(
            {"id": inv.job_card_id},
            {"$set": {"status": "invoiced", "invoice_id": inv.id, "updated_at": now_iso()}},
        )
    return inv.model_dump()