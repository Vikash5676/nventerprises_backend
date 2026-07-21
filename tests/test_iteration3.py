"""
Iteration 3 backend tests:
- Shop settings (GET/PUT /api/shop/info, owner RBAC)
- Discount on invoice preview + create (persistence, edges)
- Dashboard + Customers aggregation shape & perf regression
- Regression: prior endpoints still work (light checks)
"""
import os
import time
from datetime import datetime, timezone

import pytest
import requests
from dotenv import load_dotenv

load_dotenv("/app/frontend/.env")
BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "owner@garage.in"
ADMIN_PASSWORD = "admin123"


# ---------------------------- Fixtures ----------------------------
@pytest.fixture(scope="module")
def token():
    r = requests.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=15)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    return r.json()["token"]


@pytest.fixture(scope="module")
def auth_headers(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


# ---------------------------- Shop Settings ----------------------------
class TestShopSettings:
    def test_get_shop_info_bootstraps(self):
        r = requests.get(f"{API}/shop/info", timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        for k in ["name", "tagline", "logo_base64", "address", "phone", "gstin", "state"]:
            assert k in d, f"missing {k}"
        assert d["name"]  # non-empty after bootstrap
        assert "_id" not in d

    def test_put_shop_info_requires_auth(self):
        r = requests.put(f"{API}/shop/info", json={"name": "X", "state": "Jharkhand"}, timeout=15)
        assert r.status_code == 401

    def test_put_shop_info_owner_updates(self, auth_headers):
        # Get current settings first
        current = requests.get(f"{API}/shop/info", timeout=15).json()
        new = dict(current)
        new["tagline"] = "TEST Tagline v3"
        new["name"] = "TEST_ShopName_v3"
        r = requests.put(f"{API}/shop/info", headers=auth_headers, json=new, timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["tagline"] == "TEST Tagline v3"
        assert d["name"] == "TEST_ShopName_v3"

        # GET again to verify persistence
        r2 = requests.get(f"{API}/shop/info", timeout=15)
        assert r2.status_code == 200
        assert r2.json()["tagline"] == "TEST Tagline v3"

        # restore
        requests.put(f"{API}/shop/info", headers=auth_headers, json=current, timeout=15)

    def test_shop_state_change_affects_gst(self, auth_headers):
        """PUT state=Maharashtra -> subsequent invoice for Jharkhand customer becomes inter-state IGST."""
        current = requests.get(f"{API}/shop/info", timeout=15).json()
        try:
            new = dict(current)
            new["state"] = "Maharashtra"
            r = requests.put(f"{API}/shop/info", headers=auth_headers, json=new, timeout=15)
            assert r.status_code == 200
            # preview an invoice with customer_state=Jharkhand -> should be IGST
            body = {
                "customer_name": "T", "customer_state": "Jharkhand",
                "lines": [{"name": "Item", "item_type": "part", "qty": 1, "unit_price": 1000, "gst_rate": 18}],
            }
            p = requests.post(f"{API}/invoices/preview", headers=auth_headers, json=body, timeout=15).json()
            assert p["cgst_total"] == 0.0
            assert p["sgst_total"] == 0.0
            assert p["igst_total"] == 180.0
        finally:
            requests.put(f"{API}/shop/info", headers=auth_headers, json=current, timeout=15)

        # After restoring to Jharkhand, same body -> CGST+SGST
        p = requests.post(f"{API}/invoices/preview", headers=auth_headers, json=body, timeout=15).json()
        assert p["cgst_total"] == 90.0
        assert p["sgst_total"] == 90.0
        assert p["igst_total"] == 0.0


# ---------------------------- Discount on preview & create ----------------------------
class TestDiscount:
    def _oil_cart(self, disc_type="", disc_value=0):
        return {
            "customer_name": "Disc Test",
            "customer_state": "Jharkhand",
            "lines": [{"name": "Oil", "item_type": "part", "qty": 2, "unit_price": 100, "gst_rate": 18}],
            "discount_type": disc_type,
            "discount_value": disc_value,
        }

    def test_preview_percent_10_two_oils(self, auth_headers):
        r = requests.post(f"{API}/invoices/preview", headers=auth_headers, json=self._oil_cart("percent", 10), timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["gross_subtotal"] == 200.0
        assert d["discount_total"] == 20.0
        assert d["subtotal"] == 180.0
        assert d["cgst_total"] == 16.20
        assert d["sgst_total"] == 16.20
        assert d["grand_total"] == 212.40

    def test_preview_amount_50(self, auth_headers):
        r = requests.post(f"{API}/invoices/preview", headers=auth_headers, json=self._oil_cart("amount", 50), timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert d["gross_subtotal"] == 200.0
        assert d["discount_total"] == 50.0
        assert d["subtotal"] == 150.0
        assert d["cgst_total"] == 13.50
        assert d["sgst_total"] == 13.50
        assert d["grand_total"] == 177.00

    def test_preview_zero_and_empty(self, auth_headers):
        # value=0
        d = requests.post(f"{API}/invoices/preview", headers=auth_headers, json=self._oil_cart("percent", 0), timeout=15).json()
        assert d["discount_total"] == 0.0
        assert d["subtotal"] == 200.0
        # type=''
        d2 = requests.post(f"{API}/invoices/preview", headers=auth_headers, json=self._oil_cart("", 50), timeout=15).json()
        assert d2["discount_total"] == 0.0
        assert d2["subtotal"] == 200.0

    def test_preview_percent_clamped_to_100(self, auth_headers):
        d = requests.post(f"{API}/invoices/preview", headers=auth_headers, json=self._oil_cart("percent", 150), timeout=15).json()
        assert d["discount_total"] == 200.0  # clamped to 100% of 200
        assert d["subtotal"] == 0.0
        assert d["grand_total"] == 0.0

    def test_preview_amount_clamped_to_gross(self, auth_headers):
        d = requests.post(f"{API}/invoices/preview", headers=auth_headers, json=self._oil_cart("amount", 5000), timeout=15).json()
        assert d["discount_total"] == 200.0
        assert d["subtotal"] == 0.0
        assert d["grand_total"] == 0.0

    def test_create_invoice_persists_discount_fields(self, auth_headers):
        r = requests.post(f"{API}/invoices", headers=auth_headers, json=self._oil_cart("percent", 10), timeout=15)
        assert r.status_code == 200, r.text
        inv = r.json()
        assert inv["gross_subtotal"] == 200.0
        assert inv["discount_type"] == "percent"
        assert inv["discount_value"] == 10
        assert inv["discount_total"] == 20.0
        assert inv["subtotal"] == 180.0
        assert inv["grand_total"] == 212.40
        # GET back
        r2 = requests.get(f"{API}/invoices/{inv['id']}", headers=auth_headers, timeout=15)
        assert r2.status_code == 200
        d = r2.json()
        assert d["gross_subtotal"] == 200.0
        assert d["discount_type"] == "percent"
        assert d["discount_total"] == 20.0

    def test_no_discount_baseline(self, auth_headers):
        r = requests.post(f"{API}/invoices/preview", headers=auth_headers, json=self._oil_cart(), timeout=15).json()
        assert r["gross_subtotal"] == 200.0
        assert r["discount_total"] == 0.0
        assert r["subtotal"] == 200.0
        assert r["cgst_total"] == 18.0
        assert r["sgst_total"] == 18.0
        assert r["grand_total"] == 236.0


# ---------------------------- Dashboard & Customers perf/shape ----------------------------
class TestDashboardPerf:
    def test_dashboard_shape_and_perf(self, auth_headers):
        start = time.time()
        r = requests.get(f"{API}/dashboard", headers=auth_headers, timeout=15)
        elapsed_ms = (time.time() - start) * 1000
        assert r.status_code == 200
        d = r.json()
        for k in ["sales_today", "expenses_today", "active_bikes", "pending_udhaar",
                  "active_vehicles", "recent_invoices", "sales_trend", "low_stock"]:
            assert k in d, f"dashboard missing {k}"
        assert len(d["sales_trend"]) == 7
        assert isinstance(d["low_stock"], list)
        # Allow generous ceiling (ingress + cold Mongo). Aggregation should be <500ms typical.
        print(f"dashboard latency: {elapsed_ms:.0f}ms")
        assert elapsed_ms < 3000, f"dashboard too slow: {elapsed_ms:.0f}ms"


class TestCustomersPerf:
    def test_customers_shape_sorted_by_udhaar(self, auth_headers):
        start = time.time()
        r = requests.get(f"{API}/customers", headers=auth_headers, timeout=15)
        elapsed_ms = (time.time() - start) * 1000
        assert r.status_code == 200
        rows = r.json()
        print(f"customers latency: {elapsed_ms:.0f}ms, rows={len(rows)}")
        assert elapsed_ms < 3000, f"customers too slow: {elapsed_ms:.0f}ms"
        if rows:
            for k in ["phone", "name", "vehicle_numbers", "invoice_count", "total_billed", "total_udhaar", "last_visit"]:
                assert k in rows[0], f"missing {k}"
            assert isinstance(rows[0]["vehicle_numbers"], list)
            # sorted desc by total_udhaar
            for i in range(len(rows) - 1):
                assert rows[i]["total_udhaar"] >= rows[i + 1]["total_udhaar"], "not sorted by total_udhaar desc"


# ---------------------------- Light regression ----------------------------
class TestRegression:
    def test_inventory_list(self, auth_headers):
        r = requests.get(f"{API}/inventory", headers=auth_headers, timeout=15)
        assert r.status_code == 200
        assert len(r.json()) >= 10

    def test_jobcards_list(self, auth_headers):
        r = requests.get(f"{API}/jobcards", headers=auth_headers, timeout=15)
        assert r.status_code == 200

    def test_staff_list(self, auth_headers):
        r = requests.get(f"{API}/staff", headers=auth_headers, timeout=15)
        assert r.status_code == 200
        assert len(r.json()) >= 4

    def test_gstr1(self, auth_headers):
        month = datetime.now(timezone.utc).strftime("%Y-%m")
        r = requests.get(f"{API}/reports/gstr1", headers=auth_headers, params={"month": month}, timeout=15)
        assert r.status_code == 200

    def test_gstr3b(self, auth_headers):
        month = datetime.now(timezone.utc).strftime("%Y-%m")
        r = requests.get(f"{API}/reports/gstr3b", headers=auth_headers, params={"month": month}, timeout=15)
        assert r.status_code == 200

    def test_gstr1_json(self, auth_headers):
        month = datetime.now(timezone.utc).strftime("%Y-%m")
        r = requests.get(f"{API}/reports/gstr1.json", headers=auth_headers, params={"month": month}, timeout=15)
        assert r.status_code == 200

    def test_mechanic_login(self):
        r = requests.post(f"{API}/mechanic/login", json={"pin": "1001"}, timeout=15)
        assert r.status_code == 200
