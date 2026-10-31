"""Browser verification of the shipped JS module against the test database only."""
from django.conf import settings
from django.http import HttpResponse
from django.urls import include, path


def module(request):
    return HttpResponse((settings.BASE_DIR / "examples" / "auth-client.js").read_text(encoding="utf-8"), content_type="text/javascript")


def harness(request):
    response = HttpResponse('''<!doctype html><html lang="en"><meta charset="utf-8">
<title>Authentication API verification</title>
<h1>Local API verification</h1><p>Isolated test database. This is not the product frontend.</p>
<pre id="results">Running browser checks...</pre>
<script type="module">
import {signup, login, logout, currentUser, apiRequest, requestPasswordReset, ApiError}
  from './auth-client.js';
const results = [];
const check = (name, passed) => {
  results.push(`${passed ? 'PASS' : 'FAIL'} ${name}`);
  document.querySelector('#results').textContent = results.join('\\n');
  if (!passed) throw new Error(name);
};
try {
  const email = `browser-${crypto.randomUUID()}@example.com`;
  const password = `Aa!${crypto.randomUUID()}`;
  try { await currentUser(); check('Anonymous API denied', false); }
  catch (error) { check('Anonymous API denied with 403', error instanceof ApiError && error.status === 403); }
  const created = await signup(email, password);
  check('Signup creates customer', created.role === 'customer');
  const user = await login(email, password);
  check('Login session works', (await currentUser()).id === user.id);
  const unsafe = await fetch('/api/auth/logout/', {
    method: 'POST', credentials: 'same-origin',
    headers: {'Content-Type': 'application/json'}, body: '{}',
  });
  check('Cookie alone cannot bypass CSRF', unsafe.status === 403);
  try {
    await apiRequest('/api/admin/staff/', {method: 'POST', data: {email: 'forbidden@example.com', password}});
    check('Customer cannot create staff', false);
  } catch (error) { check('Customer cannot create staff', error instanceof ApiError && error.status === 403); }
  await logout();
  try { await currentUser(); check('Logout invalidates session', false); }
  catch (error) { check('Logout invalidates session', error instanceof ApiError && error.status === 403); }
  const reset = await requestPasswordReset('absent-browser-check@example.com');
  check('Reset returns generic acknowledgement', reset.detail.startsWith('If an eligible account exists'));
  results.push('COMPLETE: 7 browser checks passed.');
} catch (error) {
  results.push(`ERROR: ${error.name}. Inspect server/test results; no form credentials are printed.`);
}
document.querySelector('#results').textContent = results.join('\\n');
</script></html>''')
    response["X-Auth-Verification"] = "isolated-test"
    return response


urlpatterns = [
    path("", include("config.urls")),
    path("__verification__/", harness),
    path("__verification__/auth-client.js", module),
]
