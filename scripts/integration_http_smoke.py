"""Real HTTP/session verification against the named isolated seeded demo only."""
import http.cookiejar
import json
from pathlib import Path
import urllib.error
import urllib.request

ROOT = "http://127.0.0.1:8004"
PROJECT = Path(__file__).resolve().parent.parent


def main():
    marker = json.load(urllib.request.urlopen(ROOT + "/__demo__/"))
    if marker != {"isolated_demo": "test_subscription_demo"}:
        raise SystemExit("Refusing a server without the isolated demo marker.")
    credentials = json.loads((PROJECT / ".local" / "demo-browser.json").read_text())
    owners = {}
    customer_clients = {}
    for role in ("staff", "customer-a", "customer-b"):
        opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        def get(path):
            return json.load(opener.open(ROOT + path))
        token = get("/api/auth/csrf/")["csrfToken"]
        request = urllib.request.Request(ROOT + "/api/auth/login/", data=json.dumps(credentials[role]).encode(), headers={"Content-Type": "application/json", "X-CSRFToken": token})
        user = json.load(opener.open(request))
        if role == "staff":
            summary = get("/api/billing/dashboard/summary/")
            assert summary["billed_revenue"] == "5822.40", summary
            assert summary["payments_collected"] == "2440.80", summary
            assert summary["total_outstanding"] == "3381.60", summary
            print("PASS: real HTTP staff summary reconciles confirmed/paid/cancelled invoices and partial payments")
            for path in ("/manage/", "/dashboard/", "/static/subscriptions/manage.js", "/static/subscriptions/manage.css", "/static/dashboard/dashboard.js"):
                assert opener.open(ROOT + path).status == 200
            print("PASS: real HTTP management/dashboard pages and shipped assets")
        else:
            subs, invoices, payments = [get(path) for path in ("/api/my/subscriptions/", "/api/billing/my/invoices/", "/api/billing/my/payments/")]
            assert subs["count"] == 1 and invoices["count"] == 2
            assert all(row["customer"] == user["id"] for row in subs["results"] + invoices["results"])
            assert payments["count"] == (2 if role == "customer-a" else 0)
            owners[role] = {"subscription": subs["results"][0]["id"], "invoice": invoices["results"][0]["id"]}
            customer_clients[role] = opener
            forbidden = urllib.request.Request(ROOT + "/api/subscriptions/", data=b"{}", headers={"Content-Type": "application/json"})
            try:
                opener.open(forbidden)
                raise AssertionError("Expected CSRF/role rejection")
            except urllib.error.HTTPError as error:
                assert error.code == 403
            print("PASS: real HTTP", role, "own subscriptions/invoices/payments only; unauthorized write denied")
    for role, other in (("customer-a", "customer-b"), ("customer-b", "customer-a")):
        for path in (f'/api/my/subscriptions/{owners[other]["subscription"]}/', f'/api/billing/invoices/{owners[other]["invoice"]}/', f'/api/billing/invoices/{owners[other]["invoice"]}/print/'):
            try:
                customer_clients[role].open(ROOT + path)
                raise AssertionError("Cross-customer read was allowed")
            except urllib.error.HTTPError as error:
                assert error.code == 404
    print("PASS: real HTTP A/B subscription, invoice and print detail isolation")
    print("HTTP integration checks complete; browser rendering was not tested.")


if __name__ == "__main__":
    main()
