document.querySelectorAll('[data-auth-form]').forEach((form) => {
  form.addEventListener('submit', (event) => {
    if (form.dataset.submitting) { event.preventDefault(); return; }
    form.dataset.submitting = 'true';
    const button = form.querySelector('button[type="submit"]');
    button.disabled = true;
    button.textContent = 'Memeriksa…';
  });
});
window.addEventListener('pageshow', (event) => { if (event.persisted) window.location.reload(); });
