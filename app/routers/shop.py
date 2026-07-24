from fastapi import APIRouter, HTTPException, Depends
from app.database import db
from app.config import settings
from app.models.erp import ShopSettings
from app.utils.auth import get_current_user
from app.utils.gst import clear_shop_cache, update_shop_cache

router = APIRouter(prefix="/shop", tags=["Shop"])

@router.get("/info")
async def shop_info():
    doc = await db.settings.find_one({"id": "shop"}, {"_id": 0})
    if not doc:
        doc = ShopSettings(
            name=settings.SHOP_INFO["name"],
            address=settings.SHOP_INFO["address"],
            phone=settings.SHOP_INFO["phone"],
            gstin=settings.SHOP_INFO["gstin"],
            state=settings.SHOP_INFO["state"],
        ).model_dump()
        doc["id"] = "shop"
        await db.settings.insert_one(doc)
        doc.pop("_id", None)
        update_shop_cache(doc)
    return doc

@router.put("/info")
async def update_shop_info(body: ShopSettings, user=Depends(get_current_user)):
    if user.get("role") != "owner":
        raise HTTPException(403, detail="Only owner can update shop settings")
    data = body.model_dump()
    data["id"] = "shop"
    await db.settings.update_one({"id": "shop"}, {"$set": data}, upsert=True)
    clear_shop_cache()
    update_shop_cache(data)
    return data