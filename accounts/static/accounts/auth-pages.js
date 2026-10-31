import {
  ApiError, signup, login, logout, currentUser, apiRequest,
  requestPasswordReset, confirmPasswordReset,
} from './auth-client.js';

const page = document.body.dataset.page;
const feedback = document.querySelector('#feedback');
const form = document.querySelector('#auth-form');

function message(text, success = false) {
  feedback.textContent = text;
  feedback.classList.toggle('success', success);
  feedback.hidden = false;
  feedback.focus();
}

function report(error) {
  if (error instanceof ApiError) {
    const text = Object.entries(error.errors).map(([key, value]) =>
      `${key === 'detail' || key === 'non_field_errors' ? '' : `${key.replaceAll('_', ' ')}: `}${Array.isArray(value) ? value.join(' ') : value}`
    ).join('\n');
    message(text || 'The request could not be completed. Please try again.');
  } else {
    message('Unable to complete the request. Check your connection and try again.');
  }
}

function setBusy(target, busy) {
  for (const button of target.querySelectorAll('button')) button.disabled = busy;
  target.setAttribute('aria-busy', String(busy));
}

let resetUid, resetToken;
if (page === 'reset_password') {
  const params = new URLSearchParams(window.location.hash.slice(1) || window.location.search.slice(1));
  resetUid = params.get('uid');
  resetToken = params.get('token');
  // Remove reset credentials from the visible URL/history before requests.
  window.history.replaceState(null, '', window.location.pathname);
  if (!resetUid || !resetToken) {
    message('This reset link is incomplete. Request a new link to continue.');
    setBusy(form, true);
  }
}

form?.addEventListener('submit', async event => {
  event.preventDefault();
  const email = form.querySelector('[name=email]')?.value;
  const passwordInput = form.querySelector('[name=password]');
  const password = passwordInput?.value;
  const confirm = form.querySelector('#confirm-password');
  if (confirm && confirm.value !== password) {
    message('The passwords do not match.');
    return;
  }
  setBusy(form, true);
  feedback.hidden = true;
  let finished = false;
  try {
    if (page === 'login') {
      await login(email, password);
      passwordInput.value = '';
      window.location.assign('/account/');
      finished = true;
    } else if (page === 'signup') {
      await signup(email, password);
      form.reset();
      message('Your account is ready. You can now sign in.', true);
      finished = true;
    } else if (page === 'password_reset') {
      const result = await requestPasswordReset(email);
      message(result.detail, true);
    } else if (page === 'reset_password') {
      const result = await confirmPasswordReset(resetUid, resetToken, password);
      form.reset();
      resetUid = resetToken = undefined;
      message(result.detail, true);
      finished = true;
    }
  } catch (error) {
    report(error);
  } finally {
    setBusy(form, false);
    if (finished) form.querySelector('button[type=submit]').disabled = true;
  }
});

if (page === 'account') {
  try {
    const user = await currentUser();
    document.querySelector('#account-email').textContent = user.email;
    document.querySelector('#account-role').textContent = user.role;
    document.querySelector('#staff-section').hidden = user.role !== 'admin';
  } catch (error) {
    if (error instanceof ApiError && error.status === 403) window.location.assign('/login/');
    else report(error);
  }
  document.querySelector('#logout').addEventListener('click', async event => {
    const button = event.currentTarget;
    button.disabled = true;
    try { await logout(); window.location.assign('/login/'); }
    catch (error) { button.disabled = false; report(error); }
  });
  const staffForm = document.querySelector('#staff-form');
  staffForm.addEventListener('submit', async event => {
    event.preventDefault();
    setBusy(staffForm, true);
    try {
      await apiRequest('/api/admin/staff/', {method: 'POST', data: {
        email: staffForm.elements.email.value, password: staffForm.elements.password.value,
      }});
      staffForm.reset();
      message('Staff account created.', true);
    } catch (error) { report(error); }
    finally { setBusy(staffForm, false); }
  });
}
