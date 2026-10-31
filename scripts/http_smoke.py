"""HTTP verification against the optional isolated test server on loopback:8001.

This is an HTTP test, not a browser rendering test. Generated test credentials
are never printed. Refuses servers without the test-harness marker.
"""
import http.cookiejar
import json
import secrets
from urllib.error import HTTPError
from urllib.request import build_opener, HTTPCookieProcessor, Request

BASE = "http://127.0.0.1:8001"
opener = build_opener(HTTPCookieProcessor(http.cookiejar.CookieJar()))
passed = 0


def request(path, method="GET", data=None, token=None):
    headers = {"Accept": "application/json", "Origin": BASE}
    if data is not None:
        headers["Content-Type"] = "application/json"
    if token:
        headers["X-CSRFToken"] = token
    req = Request(BASE + path, method=method, headers=headers,
                  data=None if data is None else json.dumps(data).encode())
    try:
        response = opener.open(req, timeout=10)
    except HTTPError as exc:
        response = exc
    with response:
        return response.status, response.read(), response.headers


def check(name, condition):
    global passed
    if not condition:
        raise SystemExit(f"FAIL: {name}. No credentials printed.")
    passed += 1
    print(f"PASS: {name}")


def csrf():
    status, body, _ = request("/api/auth/csrf/")
    if status != 200:
        raise SystemExit("CSRF initialization failed.")
    return json.loads(body)["csrfToken"]


def main():
    status, _, headers = request("/__verification__/")
    if status != 200 or headers.get("X-Auth-Verification") != "isolated-test":
        raise SystemExit("Refusing to create test accounts: isolated verification marker missing.")
    for path in ["/login/", "/signup/", "/password-reset/", "/reset-password/",
                 "/static/accounts/auth.css", "/static/accounts/auth-client.js", "/static/accounts/auth-pages.js"]:
        status, body, _ = request(path)
        check(f"HTTP resource {path}", status == 200 and bool(body))
    status, _, _ = request("/api/auth/me/")
    check("anonymous session denied with 403", status == 403)
    email = f"http-smoke-{secrets.token_hex(8)}@example.com"
    password = "Aa!" + secrets.token_urlsafe(24)
    status, body, _ = request("/api/auth/signup/", "POST", {"email": email, "password": password}, csrf())
    check("signup creates customer", status == 201 and json.loads(body)["role"] == "customer")
    status, _, _ = request("/api/auth/login/", "POST", {"email": email, "password": password}, csrf())
    check("login succeeds", status == 200)
    status, body, _ = request("/api/auth/me/")
    check("HTTP cookie session persists", status == 200 and json.loads(body)["email"] == email)
    status, _, _ = request("/api/admin/staff/", "POST", {"email": "forbidden@example.com", "password": password}, csrf())
    check("customer staff creation denied", status == 403)
    status, _, _ = request("/api/auth/logout/", "POST", {})
    check("CSRF-less logout denied", status == 403)
    status, _, _ = request("/api/auth/logout/", "POST", {}, csrf())
    check("logout succeeds", status == 204)
    status, _, _ = request("/api/auth/me/")
    check("logged-out session denied", status == 403)
    status, body, _ = request("/api/auth/password-reset/", "POST", {"email": email}, csrf())
    other_status, other_body, _ = request("/api/auth/password-reset/", "POST", {"email": "unknown-smoke@example.com"}, csrf())
    check("reset response remains generic", status == other_status == 202 and body == other_body)
    print(f"HTTP smoke: {passed} checks passed. Browser rendering not tested.")


if __name__ == "__main__":
    main()
