from typing import Dict, Any
from app.database import db
from app.config import settings

_SHOP_CACHE: Dict[str, Any] = {}

async def get_shop_state() -> str:
    if "state" in _SHOP_CACHE:
        return _SHOP_CACHE["state"]
    doc = await db.settings.find_one({"id": "shop"}, {"_id": 0})
    if doc:
        _SHOP_CACHE.update(doc)
        return doc.get("state", "Jharkhand")
    return settings.SHOP_INFO["state"]

def clear_shop_cache():
    _SHOP_CACHE.clear()

def update_shop_cache(data: dict):
    _SHOP_CACHE.update(data)

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
    raw_lines = []
    for l in payload["lines"]:
        raw = dict(l)
        raw["_base_taxable"] = round(float(raw.get("qty", 0)) * float(raw.get("unit_price", 0)), 2)
        raw_lines.append(raw)
    base_subtotal = round(sum(r["_base_taxable"] for r in raw_lines), 2)

    disc_type = (payload.get("discount_type") or "").lower()
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