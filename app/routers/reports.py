from fastapi import APIRouter, Depends
from app.database import db
from app.config import settings
from app.utils.auth import get_current_user

router = APIRouter(prefix="/reports", tags=["Reports"])

@router.get("/gstr1")
async def gstr1(month: str, user=Depends(get_current_user)):
    invoices = await db.invoices.find({"created_at": {"$regex": f"^{month}"}}, {"_id": 0}).to_list(5000)
    rows = []
    total_taxable, total_cgst, total_sgst, total_igst, total = 0.0, 0.0, 0.0, 0.0, 0.0
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

@router.get("/gstr3b")
async def gstr3b(month: str, user=Depends(get_current_user)):
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

@router.get("/gstr1.json")
async def gstr1_portal_json(month: str, user=Depends(get_current_user)):
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
        "gstin": settings.SHOP_INFO["gstin"],
        "fp": month.replace("-", ""),
        "gt": round(sum(i["grand_total"] for i in invoices), 2),
        "cur_gt": round(sum(i["grand_total"] for i in invoices), 2),
        "b2b": b2b,
        "b2cs": list(b2cs.values()),
    }