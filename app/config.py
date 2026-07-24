import os
from pathlib import Path
from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(ROOT_DIR / ".env")

class Settings:
    MONGO_URL: str = os.environ["MONGO_URL"]
    DB_NAME: str = os.environ["DB_NAME"]
    JWT_SECRET: str = os.environ["JWT_SECRET"]
    JWT_ALGORITHM: str = "HS256"
    ADMIN_EMAIL: str = os.environ.get("ADMIN_EMAIL", "owner@garage.in")
    ADMIN_PASSWORD: str = os.environ.get("ADMIN_PASSWORD", "admin123")
    CORS_ORIGINS: list[str] = os.environ.get("CORS_ORIGINS", "*").split(",")
    
    SHOP_INFO: dict = {
        "name": os.environ.get("SHOP_NAME", "Ranchi Motors Workshop"),
        "state": os.environ.get("SHOP_STATE", "Jharkhand"),
        "gstin": os.environ.get("SHOP_GSTIN", "20ABCDE1234F1Z5"),
        "address": os.environ.get("SHOP_ADDRESS", ""),
        "phone": os.environ.get("SHOP_PHONE", ""),
    }

settings = Settings()