"""
Comprehensive backend tests for Two-Wheeler ERP.
Runs against REACT_APP_BACKEND_URL (external ingress).
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
@pytest.fixture(scope="session")
def token():
    r = requests.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=15)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    data = r.json()
    assert "token" in data and data["token"]
    return data["token"]


@pytest.fixture(scope="session")
def auth_headers(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


@pytest.fixture(scope="session")
def cookie_session():
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=15)
    assert r.status_code == 200
    return s


# ---------------------------- Auth ----------------------------
class TestAuth:
    def test_login_success_and_shape(self):
        r = requests.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert "token" in d and isinstance(d["token"], str) and len(d["token"]) > 20
        assert d["user"]["email"] == ADMIN_EMAIL
        assert d["user"]["role"] == "owner"
        assert "id" in d["user"]
        # cookie should be set
        assert "access_token" in r.cookies

    def test_login_invalid(self):
        r = requests.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": "wrong"}, timeout=15)
        assert r.status_code == 401

    def test_me_bearer(self, auth_headers):
        r = requests.get(f"{API}/auth/me", headers=auth_headers, timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert d["email"] == ADMIN_EMAIL
        assert "password_hash" not in d
        assert "_id" not in d

    def test_me_cookie(self, cookie_session):
        r = cookie_session.get(f"{API}/auth/me", timeout=15)
        assert r.status_code == 200
        assert r.json()["email"] == ADMIN_EMAIL

    def test_me_unauth(self):
        r = requests.get(f"{API}/auth/me", timeout=15)
        assert r.status_code == 401


# ---------------------------- Dashboard ----------------------------
class TestDashboard:
    def test_dashboard_shape(self, auth_headers):
        r = requests.get(f"{API}/dashboard", headers=auth_headers, timeout=15)
        assert r.status_code == 200
        d = r.json()
        for k in ["sales_today", "expenses_today", "active_bikes", "pending_udhaar", "active_vehicles", "recent_invoices"]:
            assert k in d, f"missing {k}"
        assert isinstance(d["active_vehicles"], list)
        assert isinstance(d["recent_invoices"], list)


# ---------------------------- Inventory ----------------------------
class TestInventory:
    def test_list_inventory_seeded(self, auth_headers):
        r = requests.get(f"{API}/inventory", headers=auth_headers, timeout=15)
        assert r.status_code == 200
        items = r.json()
        assert isinstance(items, list)
        assert len(items) >= 14, f"expected >=14 seeded, got {len(items)}"
        # check some seeded values present
        names = [i["name"] for i in items]
        assert any("Engine Oil" in n for n in names)
        assert any("Clutch Plate" in n for n in names)

    def test_search_by_name(self, auth_headers):
        r = requests.get(f"{API}/inventory", headers=auth_headers, params={"q": "Engine"}, timeout=15)
        assert r.status_code == 200
        items = r.json()
        assert len(items) >= 1
        for it in items:
            # some may match hsn_sac; just require name filter isn't broken
            pass
        assert any("Engine" in it["name"] for it in items)

    def test_search_by_barcode(self, auth_headers):
        r = requests.get(f"{API}/inventory", headers=auth_headers, params={"q": "8901030100011"}, timeout=15)
        assert r.status_code == 200
        items = r.json()
        assert len(items) == 1
        assert items[0]["barcode"] == "8901030100011"

    def test_create_update_delete(self, auth_headers):
        payload = {
            "name": "TEST_Widget",
            "item_type": "part",
            "hsn_sac": "0000",
            "stock": 10,
            "unit_price": 100,
            "low_stock_threshold": 2,
            "rack_location": "TEST",
            "gst_rate": 18,
            "barcode": "TEST_BC_001",
        }
        r = requests.post(f"{API}/inventory", headers=auth_headers, json=payload, timeout=15)
        assert r.status_code == 200
        created = r.json()
        assert created["name"] == "TEST_Widget"
        assert "id" in created
        iid = created["id"]

        # update
        payload["unit_price"] = 150
        payload["stock"] = 20
        r2 = requests.put(f"{API}/inventory/{iid}", headers=auth_headers, json=payload, timeout=15)
        assert r2.status_code == 200
        assert r2.json()["unit_price"] == 150

        # get via list
        r3 = requests.get(f"{API}/inventory", headers=auth_headers, params={"q": "TEST_Widget"}, timeout=15)
        assert r3.status_code == 200
        found = [i for i in r3.json() if i["id"] == iid]
        assert found and found[0]["stock"] == 20

        # delete
        r4 = requests.delete(f"{API}/inventory/{iid}", headers=auth_headers, timeout=15)
        assert r4.status_code == 200
        r5 = requests.get(f"{API}/inventory", headers=auth_headers, params={"q": "TEST_Widget"}, timeout=15)
        assert all(i["id"] != iid for i in r5.json())


# ---------------------------- Job Cards ----------------------------
class TestJobCards:
    def test_list_seeded(self, auth_headers):
        r = requests.get(f"{API}/jobcards", headers=auth_headers, timeout=15)
        assert r.status_code == 200
        cards = r.json()
        assert len(cards) >= 3

    def test_create_and_transition(self, auth_headers):
        # create
        payload = {
            "vehicle_number": "JH99TEST99",
            "model_name": "TEST Model",
            "customer_name": "TEST Customer",
            "phone": "9999999999",
            "fuel_level": 50,
            "complaints": "TEST complaint",
        }
        r = requests.post(f"{API}/jobcards", headers=auth_headers, json=payload, timeout=15)
        assert r.status_code == 200
        card = r.json()
        assert card["status"] == "checked_in"
        cid = card["id"]

        # checked_in → in_progress → ready → invoiced
        for st in ["in_progress", "ready", "invoiced"]:
            r2 = requests.put(f"{API}/jobcards/{cid}/status", headers=auth_headers, json={"status": st}, timeout=15)
            assert r2.status_code == 200
            assert r2.json()["status"] == st

        # cleanup
        requests.delete(f"{API}/jobcards/{cid}", headers=auth_headers, timeout=15)


# ---------------------------- Staff & Attendance ----------------------------
class TestStaff:
    def test_list_staff_seeded(self, auth_headers):
        r = requests.get(f"{API}/staff", headers=auth_headers, timeout=15)
        assert r.status_code == 200
        s = r.json()
        assert len(s) >= 4

    def test_attendance_toggle_and_list(self, auth_headers):
        r = requests.get(f"{API}/staff", headers=auth_headers, timeout=15)
        staff = r.json()
        sid = staff[0]["id"]
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        r1 = requests.post(f"{API}/attendance/toggle", headers=auth_headers, json={"staff_id": sid, "date": today, "present": True}, timeout=15)
        assert r1.status_code == 200
        r2 = requests.get(f"{API}/attendance", headers=auth_headers, params={"date": today}, timeout=15)
        assert r2.status_code == 200
        recs = r2.json()
        assert any(x["staff_id"] == sid and x["present"] is True for x in recs)

        # toggle to absent
        r3 = requests.post(f"{API}/attendance/toggle", headers=auth_headers, json={"staff_id": sid, "date": today, "present": False}, timeout=15)
        assert r3.status_code == 200
        r4 = requests.get(f"{API}/attendance", headers=auth_headers, params={"date": today}, timeout=15)
        assert any(x["staff_id"] == sid and x["present"] is False for x in r4.json())


# ---------------------------- Invoice preview (GST engine) ----------------------------
class TestInvoicePreview:
    def _line(self, price=1000, qty=1, gst=18, item_type="part"):
        return {"name": "TEST Item", "item_type": item_type, "qty": qty, "unit_price": price, "gst_rate": gst}

    def test_preview_jharkhand_cgst_sgst(self, auth_headers):
        body = {"customer_name": "Local", "customer_state": "Jharkhand", "lines": [self._line(1000, 1, 18)]}
        r = requests.post(f"{API}/invoices/preview", headers=auth_headers, json=body, timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert d["subtotal"] == 1000
        assert d["cgst_total"] == 90.0
        assert d["sgst_total"] == 90.0
        assert d["igst_total"] == 0.0
        assert d["grand_total"] == 1180.0

    def test_preview_maharashtra_igst(self, auth_headers):
        body = {"customer_name": "OutState", "customer_state": "Maharashtra", "lines": [self._line(1000, 1, 18)]}
        r = requests.post(f"{API}/invoices/preview", headers=auth_headers, json=body, timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert d["cgst_total"] == 0.0
        assert d["sgst_total"] == 0.0
        assert d["igst_total"] == 180.0
        assert d["grand_total"] == 1180.0


# ---------------------------- Full Invoice Creation ----------------------------
class TestInvoiceCreate:
    def test_create_invoice_decrements_stock_and_marks_jc(self, auth_headers):
        # pick a part with sufficient stock
        inv = requests.get(f"{API}/inventory", headers=auth_headers, timeout=15).json()
        part = next(x for x in inv if x["item_type"] == "part" and x["stock"] >= 2)
        pid = part["id"]
        initial_stock = part["stock"]

        # create jobcard
        jc = requests.post(f"{API}/jobcards", headers=auth_headers, json={
            "vehicle_number": "JH88TEST88", "model_name": "TEST", "customer_name": "Inv Test", "phone": "9111111111"
        }, timeout=15).json()

        body = {
            "customer_name": "Inv Test",
            "customer_state": "Jharkhand",
            "job_card_id": jc["id"],
            "lines": [{
                "item_id": pid,
                "name": part["name"],
                "item_type": "part",
                "hsn_sac": part.get("hsn_sac", ""),
                "qty": 1,
                "unit_price": part["unit_price"],
                "gst_rate": part["gst_rate"],
            }],
            "cash_amount": 0, "upi_amount": 0, "udhaar_amount": 0,
        }
        r = requests.post(f"{API}/invoices", headers=auth_headers, json=body, timeout=15)
        assert r.status_code == 200, r.text
        created = r.json()
        assert created["invoice_no"].startswith("INV-")
        parts = created["invoice_no"].split("-")
        assert len(parts) == 3 and len(parts[2]) == 5  # INV-YY-00001

        # stock decremented
        new_inv = requests.get(f"{API}/inventory", headers=auth_headers, timeout=15).json()
        updated_part = next(x for x in new_inv if x["id"] == pid)
        assert updated_part["stock"] == initial_stock - 1

        # jobcard marked invoiced
        jcs = requests.get(f"{API}/jobcards", headers=auth_headers, timeout=15).json()
        found_jc = next(x for x in jcs if x["id"] == jc["id"])
        assert found_jc["status"] == "invoiced"
        assert found_jc.get("invoice_id") == created["id"]

        # GET the invoice back
        r2 = requests.get(f"{API}/invoices/{created['id']}", headers=auth_headers, timeout=15)
        assert r2.status_code == 200
        assert r2.json()["invoice_no"] == created["invoice_no"]


# ---------------------------- Suppliers & Purchases ----------------------------
class TestSuppliersAndPurchases:
    def test_list_suppliers_seeded(self, auth_headers):
        r = requests.get(f"{API}/suppliers", headers=auth_headers, timeout=15)
        assert r.status_code == 200
        assert len(r.json()) >= 2

    def test_create_supplier_and_purchase(self, auth_headers):
        # create supplier
        s = requests.post(f"{API}/suppliers", headers=auth_headers, json={"name": "TEST_Supp", "gstin": "20TEST", "phone": "1", "address": "T"}, timeout=15).json()
        sid = s["id"]

        # pick item
        inv = requests.get(f"{API}/inventory", headers=auth_headers, timeout=15).json()
        item = next(x for x in inv if x["item_type"] == "part")
        initial_stock = item["stock"]

        exp_before = requests.get(f"{API}/expenses", headers=auth_headers, timeout=15).json()
        exp_count_before = len(exp_before)

        body = {
            "supplier_id": sid,
            "invoice_no": "TESTPO-001",
            "lines": [{"item_id": item["id"], "name": item["name"], "hsn_sac": item.get("hsn_sac", ""), "qty": 5, "unit_cost": 100}],
            "paid_amount": 200,
        }
        r = requests.post(f"{API}/purchases", headers=auth_headers, json=body, timeout=15)
        assert r.status_code == 200
        p = r.json()
        assert p["total"] == 500
        assert p["balance"] == 300

        # stock incremented by 5
        new_item = next(x for x in requests.get(f"{API}/inventory", headers=auth_headers, timeout=15).json() if x["id"] == item["id"])
        assert new_item["stock"] == initial_stock + 5

        # supplier payable_balance updated
        supp = next(x for x in requests.get(f"{API}/suppliers", headers=auth_headers, timeout=15).json() if x["id"] == sid)
        assert supp["payable_balance"] == 300

        # expense with source='purchase' created
        exps = requests.get(f"{API}/expenses", headers=auth_headers, timeout=15).json()
        assert len(exps) == exp_count_before + 1
        latest = exps[0] if exps and exps[0].get("source") == "purchase" else next((e for e in exps if e.get("source") == "purchase" and "TESTPO-001" in e.get("note", "")), None)
        assert latest is not None
        assert latest["source"] == "purchase"
        assert latest["amount"] == 500

        # cleanup
        requests.delete(f"{API}/suppliers/{sid}", headers=auth_headers, timeout=15)


# ---------------------------- Payroll ----------------------------
class TestPayroll:
    def test_payroll_month(self, auth_headers):
        month = datetime.now(timezone.utc).strftime("%Y-%m")
        r = requests.get(f"{API}/payroll", headers=auth_headers, params={"month": month}, timeout=15)
        assert r.status_code == 200
        rows = r.json()
        assert isinstance(rows, list) and len(rows) >= 4
        keys = ["staff_id", "name", "base_salary", "present_days", "prorated_base", "commission", "advances", "net_payable"]
        for row in rows:
            for k in keys:
                assert k in row, f"payroll missing {k}"

    def test_payroll_commission_ties_to_labor_invoice(self, auth_headers):
        # find a mechanic
        staff = requests.get(f"{API}/staff", headers=auth_headers, timeout=15).json()
        mech = next(s for s in staff if s.get("commission_pct", 0) > 0)
        # create a jobcard assigned to mech
        jc = requests.post(f"{API}/jobcards", headers=auth_headers, json={
            "vehicle_number": "JH77PAY77", "model_name": "T", "customer_name": "Pay Test", "phone": "911", "assigned_mechanic_id": mech["id"]
        }, timeout=15).json()
        # create invoice with labor line
        body = {
            "customer_name": "Pay Test",
            "customer_state": "Jharkhand",
            "job_card_id": jc["id"],
            "lines": [{
                "name": "TEST Labor", "item_type": "labor", "qty": 1, "unit_price": 1000, "gst_rate": 18,
            }],
        }
        inv = requests.post(f"{API}/invoices", headers=auth_headers, json=body, timeout=15)
        assert inv.status_code == 200

        month = datetime.now(timezone.utc).strftime("%Y-%m")
        pay = requests.get(f"{API}/payroll", headers=auth_headers, params={"month": month}, timeout=15).json()
        row = next(r for r in pay if r["staff_id"] == mech["id"])
        # commission should be at least (1000 * pct/100) added
        assert row["commission"] >= 1000 * mech["commission_pct"] / 100 - 0.01


# ---------------------------- Expenses ----------------------------
class TestExpenses:
    def test_create_and_list(self, auth_headers):
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        body = {"category": "TEST_Exp", "amount": 111, "date": today, "note": "TEST"}
        r = requests.post(f"{API}/expenses", headers=auth_headers, json=body, timeout=15)
        assert r.status_code == 200
        e = r.json()
        assert e["source"] == "manual"
        assert e["amount"] == 111
        eid = e["id"]

        r2 = requests.get(f"{API}/expenses", headers=auth_headers, timeout=15)
        assert r2.status_code == 200
        found = [x for x in r2.json() if x["id"] == eid]
        assert found

        # cleanup
        requests.delete(f"{API}/expenses/{eid}", headers=auth_headers, timeout=15)


# ---------------------------- Reports ----------------------------
class TestReports:
    def test_gstr1(self, auth_headers):
        month = datetime.now(timezone.utc).strftime("%Y-%m")
        r = requests.get(f"{API}/reports/gstr1", headers=auth_headers, params={"month": month}, timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert "rows" in d and "totals" in d
        for k in ["taxable", "cgst", "sgst", "igst", "total"]:
            assert k in d["totals"]

    def test_gstr3b(self, auth_headers):
        month = datetime.now(timezone.utc).strftime("%Y-%m")
        r = requests.get(f"{API}/reports/gstr3b", headers=auth_headers, params={"month": month}, timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert d["month"] == month
        assert "outward_supplies" in d
        for k in ["taxable", "cgst", "sgst", "igst", "total_tax"]:
            assert k in d["outward_supplies"]


# ============================================================
# ITERATION 2 - NEW P1/P2 FEATURES
# ============================================================


# ---------------------------- Mechanic PIN Login ----------------------------
class TestMechanicAuth:
    def test_mechanic_login_valid_pin(self):
        r = requests.post(f"{API}/mechanic/login", json={"pin": "1001"}, timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        assert "token" in d and isinstance(d["token"], str) and len(d["token"]) > 20
        assert d["staff"]["name"] == "Ramesh Kumar"
        assert d["staff"]["pin"] == "1001"
        assert "_id" not in d["staff"]

    def test_mechanic_login_invalid_pin(self):
        r = requests.post(f"{API}/mechanic/login", json={"pin": "0000"}, timeout=15)
        assert r.status_code == 401

    def test_mechanic_login_empty_pin(self):
        r = requests.post(f"{API}/mechanic/login", json={"pin": ""}, timeout=15)
        assert r.status_code == 400

    def test_all_seeded_pins_login(self):
        expected = {"1001": "Ramesh Kumar", "1002": "Suresh Yadav", "1003": "Prakash Singh", "1004": "Vikas Mahto"}
        for pin, name in expected.items():
            r = requests.post(f"{API}/mechanic/login", json={"pin": pin}, timeout=15)
            assert r.status_code == 200, f"PIN {pin} failed: {r.text}"
            assert r.json()["staff"]["name"] == name


# ---------------------------- Mechanic Jobs (RBAC) ----------------------------
class TestMechanicJobs:
    @pytest.fixture(scope="class")
    def mech_token_and_id(self):
        r = requests.post(f"{API}/mechanic/login", json={"pin": "1001"}, timeout=15)
        assert r.status_code == 200
        d = r.json()
        return d["token"], d["staff"]["id"]

    def test_mechanic_gets_only_own_jobs(self, mech_token_and_id):
        token, sid = mech_token_and_id
        r = requests.get(f"{API}/mechanic/jobs", headers={"Authorization": f"Bearer {token}"}, timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert "me" in d and d["me"]["id"] == sid
        assert "jobs" in d and isinstance(d["jobs"], list)
        # every job returned should be assigned to this mechanic AND not invoiced
        for jc in d["jobs"]:
            assert jc["assigned_mechanic_id"] == sid
            assert jc["status"] != "invoiced"

    def test_owner_token_rejected_on_mechanic_endpoint(self, auth_headers):
        # Owner is authenticated but not a mechanic token → 403
        r = requests.get(f"{API}/mechanic/jobs", headers=auth_headers, timeout=15)
        assert r.status_code == 403

    def test_no_auth_rejected(self):
        r = requests.get(f"{API}/mechanic/jobs", timeout=15)
        assert r.status_code == 401

    def test_mechanic_can_advance_own_job_status(self, mech_token_and_id, auth_headers):
        token, sid = mech_token_and_id
        # create a jobcard assigned to this mechanic via owner
        payload = {
            "vehicle_number": "JHMEC001", "model_name": "TEST Bike", "customer_name": "Mech Test",
            "phone": "9000000001", "assigned_mechanic_id": sid, "complaints": "test",
        }
        r = requests.post(f"{API}/jobcards", headers=auth_headers, json=payload, timeout=15)
        assert r.status_code == 200
        jc = r.json()
        jid = jc["id"]

        # mechanic advances status
        r2 = requests.post(f"{API}/mechanic/jobs/{jid}/status",
                           headers={"Authorization": f"Bearer {token}"},
                           json={"status": "in_progress"}, timeout=15)
        assert r2.status_code == 200
        assert r2.json()["status"] == "in_progress"

        # verify persisted
        r3 = requests.get(f"{API}/jobcards", headers=auth_headers, timeout=15)
        found = next(x for x in r3.json() if x["id"] == jid)
        assert found["status"] == "in_progress"

        # cleanup
        requests.delete(f"{API}/jobcards/{jid}", headers=auth_headers, timeout=15)

    def test_mechanic_cannot_advance_others_job(self, mech_token_and_id, auth_headers):
        token, sid = mech_token_and_id
        # find another mechanic
        staff = requests.get(f"{API}/staff", headers=auth_headers, timeout=15).json()
        other = next(s for s in staff if s["id"] != sid and s.get("pin"))
        # create job for OTHER mechanic
        r = requests.post(f"{API}/jobcards", headers=auth_headers, json={
            "vehicle_number": "JHOTH999", "model_name": "T", "customer_name": "Other",
            "phone": "9000000002", "assigned_mechanic_id": other["id"],
        }, timeout=15)
        jc = r.json()
        jid = jc["id"]

        # PIN 1001 tries to update it → should 404
        r2 = requests.post(f"{API}/mechanic/jobs/{jid}/status",
                           headers={"Authorization": f"Bearer {token}"},
                           json={"status": "in_progress"}, timeout=15)
        assert r2.status_code == 404

        # cleanup
        requests.delete(f"{API}/jobcards/{jid}", headers=auth_headers, timeout=15)


# ---------------------------- Customers Aggregate ----------------------------
class TestCustomers:
    def test_list_customers_shape(self, auth_headers):
        r = requests.get(f"{API}/customers", headers=auth_headers, timeout=15)
        assert r.status_code == 200
        rows = r.json()
        assert isinstance(rows, list)
        if rows:
            row = rows[0]
            for k in ["phone", "name", "vehicle_numbers", "invoice_count", "total_billed", "total_udhaar", "last_visit"]:
                assert k in row, f"customers missing {k}"
            assert isinstance(row["vehicle_numbers"], list)

    def test_customer_ledger(self, auth_headers):
        # get any customer with a phone that has invoices
        rows = requests.get(f"{API}/customers", headers=auth_headers, timeout=15).json()
        with_phone = [c for c in rows if c.get("phone")]
        if not with_phone:
            pytest.skip("no customer with phone to check ledger")
        phone = with_phone[0]["phone"]
        r = requests.get(f"{API}/customers/{phone}/ledger", headers=auth_headers, timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert d["phone"] == phone
        assert isinstance(d["invoices"], list)
        assert isinstance(d["job_cards"], list)
        assert "total_billed" in d and "total_udhaar" in d


# ---------------------------- Dashboard NEW keys ----------------------------
class TestDashboardExtended:
    def test_sales_trend_7_days(self, auth_headers):
        r = requests.get(f"{API}/dashboard", headers=auth_headers, timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert "sales_trend" in d
        assert len(d["sales_trend"]) == 7
        for pt in d["sales_trend"]:
            for k in ["date", "label", "sales", "count"]:
                assert k in pt, f"trend point missing {k}"

    def test_low_stock_array(self, auth_headers):
        r = requests.get(f"{API}/dashboard", headers=auth_headers, timeout=15)
        d = r.json()
        assert "low_stock" in d
        assert isinstance(d["low_stock"], list)
        # every item should have stock <= threshold
        for it in d["low_stock"]:
            assert it["stock"] <= it["low_stock_threshold"]


# ---------------------------- Bulk Import ----------------------------
class TestInventoryBulkImport:
    def test_bulk_import_creates_and_updates(self, auth_headers):
        body = {
            "rows": [
                {"name": "TEST_Bulk_A", "item_type": "part", "hsn_sac": "1234", "stock": 5,
                 "unit_price": 100, "low_stock_threshold": 2, "rack_location": "X",
                 "gst_rate": 18, "barcode": "TEST_BC_BULK_A"},
                {"name": "TEST_Bulk_B", "item_type": "part", "hsn_sac": "1234", "stock": 10,
                 "unit_price": 200, "low_stock_threshold": 3, "rack_location": "Y",
                 "gst_rate": 28, "barcode": "TEST_BC_BULK_B"},
            ],
            "upsert_by_barcode": True,
        }
        r = requests.post(f"{API}/inventory/bulk_import", headers=auth_headers, json=body, timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert d["created"] == 2 and d["updated"] == 0

        # Run again with same barcodes but new prices → should update, not create
        body["rows"][0]["unit_price"] = 150
        body["rows"][1]["stock"] = 25
        r2 = requests.post(f"{API}/inventory/bulk_import", headers=auth_headers, json=body, timeout=15)
        assert r2.status_code == 200
        d2 = r2.json()
        assert d2["updated"] == 2 and d2["created"] == 0

        # verify persistence
        items = requests.get(f"{API}/inventory", headers=auth_headers, params={"q": "TEST_Bulk"}, timeout=15).json()
        a = next(x for x in items if x["barcode"] == "TEST_BC_BULK_A")
        b = next(x for x in items if x["barcode"] == "TEST_BC_BULK_B")
        assert a["unit_price"] == 150
        assert b["stock"] == 25

        # cleanup
        requests.delete(f"{API}/inventory/{a['id']}", headers=auth_headers, timeout=15)
        requests.delete(f"{API}/inventory/{b['id']}", headers=auth_headers, timeout=15)


# ---------------------------- GSTR-1 Portal JSON ----------------------------
class TestGSTR1PortalJSON:
    def test_gstr1_json_shape(self, auth_headers):
        month = datetime.now(timezone.utc).strftime("%Y-%m")
        r = requests.get(f"{API}/reports/gstr1.json", headers=auth_headers, params={"month": month}, timeout=15)
        assert r.status_code == 200
        d = r.json()
        for k in ["gstin", "fp", "gt", "b2b", "b2cs"]:
            assert k in d, f"missing {k}"
        assert d["fp"] == month.replace("-", "")
        assert isinstance(d["b2b"], list)
        assert isinstance(d["b2cs"], list)


# ---------------------------- Staff PIN field ----------------------------
class TestStaffPIN:
    def test_staff_has_pin_field(self, auth_headers):
        r = requests.get(f"{API}/staff", headers=auth_headers, timeout=15)
        staff = r.json()
        # Seeded staff should have PINs 1001-1004
        pins = {s["name"]: s.get("pin") for s in staff if s["name"] in ("Ramesh Kumar", "Suresh Yadav", "Prakash Singh", "Vikas Mahto")}
        assert pins.get("Ramesh Kumar") == "1001"
        assert pins.get("Suresh Yadav") == "1002"
        assert pins.get("Prakash Singh") == "1003"
        assert pins.get("Vikas Mahto") == "1004"

    def test_create_staff_with_pin_can_login(self, auth_headers):
        pin = "9876"
        body = {"name": "TEST_PinStaff", "role": "Mechanic", "phone": "9000000099",
                "base_salary": 12000, "commission_pct": 20, "pin": pin}
        r = requests.post(f"{API}/staff", headers=auth_headers, json=body, timeout=15)
        assert r.status_code == 200
        s = r.json()
        assert s["pin"] == pin

        # try mechanic login with this PIN
        r2 = requests.post(f"{API}/mechanic/login", json={"pin": pin}, timeout=15)
        assert r2.status_code == 200
        assert r2.json()["staff"]["name"] == "TEST_PinStaff"

        # cleanup
        requests.delete(f"{API}/staff/{s['id']}", headers=auth_headers, timeout=15)

