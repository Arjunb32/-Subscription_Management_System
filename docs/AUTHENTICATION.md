# Authentication and teammate integration

All paths have trailing slashes. Requests and responses are JSON. Successful
user responses contain only `{ "id": 1, "email": "customer@example.com",
"role": "customer" }`; never a password/hash. Sessions use an HttpOnly cookie,
SameSite=Lax, an eight-hour expiry, and Secure cookies when DEBUG=False.

## Endpoint contract

| Method/path | Request fields | Success | Access |
|---|---|---|---|
| GET `/api/auth/csrf/` | none | 200 `{ "csrfToken": "..." }` + CSRF cookie | Public |
| POST `/api/auth/signup/` | email, password | 201 user; no automatic login | Public; always customer |
| POST `/api/auth/login/` | email, password | 200 user + session cookie | Public |
| GET `/api/auth/me/` | none | 200 user | Signed in |
| POST `/api/auth/logout/` | `{}` | 204, no response body | Signed in |
| POST `/api/admin/staff/` | email, password | 201 staff user | Application admin only |
| POST `/api/auth/password-reset/` | email | 202 generic acknowledgement | Public |
| POST `/api/auth/password-reset/confirm/` | uid, token, new_password | 200 detail | Public; valid reset token |

Unknown request fields, including role/internal privilege fields, are rejected.
Email is trimmed/lowercased and database-unique irrespective of case. Passwords
need at least nine characters, uppercase, lowercase, and a non-alphanumeric,
non-whitespace special character. The API accepts at most 1024 password characters.
Password rules apply to signup, staff creation, initial-admin creation and reset.

Errors follow DRF conventions: field maps such as `{ "password": ["..."] }` or
`{ "detail": "..." }`. Malformed JSON, invalid credentials and validation errors
return 400. Inactive accounts use the same invalid-login response. Duplicate
signup emails return 400. Invalid/expired/used reset links return 400.

**SessionAuthentication returns 403, not 401, for unauthenticated protected
requests.** Role denials and CSRF failures also return 403. A customer requesting
another customer's object through a scoped queryset receives 404. Limits return
429 and `Retry-After` seconds. Unexpected server/database outages are not reported
as successful operations.

## Django authentication pages and same-origin requests

The team confirmed it is starting from scratch. Django serves `/login/`,
`/signup/`, `/password-reset/`, `/reset-password/` and `/account/`, CSS and
JavaScript at the same origin as `/api/`. No proxy, CORS package, Node install or
separate frontend server is needed. Do not serve templates from file:// or store
session credentials in localStorage. Login, signup, reset, staff creation and
logout all require CSRF.

1. Fetch `/api/auth/csrf/`, retaining its cookie and response token.
2. Send cookies and `X-CSRFToken` with POST/PATCH/PUT/DELETE requests.
3. Fetch a new CSRF token after login because Django rotates the secret.

The shared [auth-client.js](../accounts/static/accounts/auth-client.js) implements
this flow for the actual pages and supports login, logout, signup, current user,
authenticated requests and resets. [examples/auth-client.js](../examples/auth-client.js)
re-exports the same implementation for the verification harness or a same-origin
module. Forms use textContent for errors and prevent repeated submissions.

```javascript
import { login, logout, currentUser, apiRequest, ApiError } from '/static/accounts/auth-client.js';

// Inside the existing form handler; values come from the form, not source code.
try {
  await login(emailInput.value, passwordInput.value);
  passwordInput.value = '';
  const user = await currentUser();
  // Render the existing navigation using user.role.
  // When teammates add their endpoints:
  // const records = await apiRequest('/api/subscriptions/');
} catch (error) {
  if (error instanceof ApiError) {
    // Show field errors from error.errors using textContent, never innerHTML.
    // A 403 can mean no session, denied role, or invalid CSRF; inspect detail.
    // A 429 exposes Retry-After as error.retryAfter; do not automatically retry login.
  } else {
    // Report a network/unexpected-response error without printing form data.
  }
}
// await logout(); // Attach to the existing logout button.
```

If the team later chooses a separate JavaScript dev server, prefer its proxy to
preserve same-origin browser requests. For example, if it uses Vite:

```javascript
server: {
  proxy: {
    '/api': { target: 'http://127.0.0.1:8000', changeOrigin: false }
  }
}
```

Preserve the original Host/Origin headers. Keep the frontend on one hostname
(localhost or 127.0.0.1). If a proxy rewrites Host, explicitly set
`CSRF_TRUSTED_ORIGINS` to that frontend's exact origin, including its port.
`PASSWORD_RESET_URL` must point to this application's `/reset-password/` form
using the local server's hostname and port. Reset links put uid/token in a URL
fragment so they are not sent in the initial HTTP request or server access log.
The reset page reads then removes them from the visible URL.

If cross-origin deployment is genuinely necessary, first confirm the real
origins; add narrowly configured credentialed CORS and matching CSRF trust as a
separate integration change. Do not enable wildcard CORS or disable CSRF.

## Application roles and initial admin

`user.role` controls application permissions. Django `is_staff`/`is_superuser`
are separate internal flags and do not bypass application checks. Even Django's
`createsuperuser` does not grant the application admin role. No Django admin site
is exposed. There is no public role-change or application-admin-creation API.

Run once for each local database:

```powershell
.\.venv\Scripts\python.exe manage.py create_initial_admin
```

It prompts for email and a hidden, confirmed, validated password and refuses if
an application admin already exists. A transaction lock also prevents simultaneous
bootstrap attempts. It never accepts a password in command arguments or a seed file.
Use an admin's session and `/api/admin/staff/` to create staff; an API role field
cannot change the result. Application admins can also use the staff-creation
form on `/account/`; the API enforces the role even if someone unhides the form.

## Reusable ownership checks for the three feature owners

Haridev (subscriptions), Adwaith (billing/payments), and Sreehari (reporting/portal)
should use the same user foreign key and permission components. An ownership
field/lookup is a trusted server constant, never a query parameter supplied by
the client. These helpers grant record scope; each endpoint still decides which
business actions its allowed roles can perform.

```python
from django.conf import settings
from django.db import models
from rest_framework import generics, serializers
from accounts.permissions import (
    CustomerOwnershipPermission, CustomerScopedQuerysetMixin,
    customer_for_write, owned_object_or_404,
)

# In the feature owner's actual model:
# customer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)

# Integrate with the owner's actual serializer/model, not a second shared schema.
class CustomerRecordsView(CustomerScopedQuerysetMixin, generics.ListCreateAPIView):
    permission_classes = [CustomerOwnershipPermission]
    allow_staff = False  # Opt in explicitly if this endpoint permits staff.
    customer_owner_field = 'customer_id'
    # queryset = ActualModel.objects.all()
    # serializer_class = ActualSerializer

    def perform_create(self, serializer):
        serializer.save(customer=customer_for_write(
            self.request.user, serializer.validated_data.get('customer'),
            allow_staff=self.allow_staff,
        ))
```

For updates, start from a scoped queryset and call `customer_for_write` using the
submitted customer or `instance.customer` if omitted. Customers cannot reassign
ownership; staff require explicit endpoint permission; targets must be active
customer accounts. Check related records too:

```python
parent = owned_object_or_404(
    ParentModel.objects.all(), request.user, pk=parent_id, allow_staff=False,
)
```

For records whose customer is reached through a subscription, set
`customer_owner_field = 'subscription__customer_id'`. Scope aggregation/reporting
queries before calculating totals. DRF object permissions alone do not filter
list results or authorize object creation. Hiding frontend controls does not
authorize requests. The tests use separate fixture models to demonstrate reads,
writes, parent checks and isolation without implementing business features.

## Password reset and actual email delivery

Reset requests always return the same 202 message for existing/unknown/inactive
accounts. Active accounts with usable passwords receive a one-hour link built
with Django's built-in token generator and the configured trusted reset URL.
After a successful reset the token cannot be reused and existing sessions become
invalid. Confirmation locks the user so concurrent reuse succeeds once.

Development defaults to **console email**: the link appears in the local server
terminal, not the recipient's inbox. Treat links as secrets; never share terminal
output containing a real link. Automated tests use an in-memory outbox and do not
send mail.

For actual delivery set EMAIL_BACKEND to
`django.core.mail.backends.smtp.EmailBackend`, configure EMAIL_HOST/PORT/USER/
PASSWORD/USE_TLS and DEFAULT_FROM_EMAIL locally, and use an HTTPS
PASSWORD_RESET_URL in production. DEBUG=False rejects console email or an absent
SMTP host. SMTP failures do not reveal account existence; 202 does not prove
delivery. A live inbox delivery check remains required after configuring SMTP.
Delivery is synchronous, so response timing can differ; generic response content
does not promise timing indistinguishability. Add queued delivery if that stronger
property is required before launch.

## Attempt limits and deployment

Atomic, PostgreSQL-backed fixed UTC windows apply across workers:

| Operation | Limit |
|---|---|
| Login | 5/email and 30/IP per 15-minute window |
| Reset request | 3/email and 10/IP per hour |
| Reset confirmation | 20/IP per hour |
| Signup | 10/IP per hour |

Known and unknown emails consume the same counters. Keys contain HMACs rather
than raw email/IP values. Successful logins also count. Limits reset at window
boundaries; they are not sliding-window guarantees. Client identity uses
REMOTE_ADDR and ignores arbitrary X-Forwarded-For headers. Configure a trusted
reverse proxy before changing this behavior; proxy-wide limits can otherwise
affect multiple users. These limits are not network-level DoS protection.

Run the following daily with your existing scheduler to remove expired counters:

```powershell
.\.venv\Scripts\python.exe manage.py prune_auth_attempts
```

Before public deployment, use HTTPS, DEBUG=False, exact allowed hosts, tested
SMTP delivery, trusted proxy configuration and a static-file server after
`manage.py collectstatic`. Django's development server serves the assets locally.
Run `manage.py check --deploy` with the deployment's environment. No deployment,
proxy server or scheduled job is claimed to be configured by this change.
