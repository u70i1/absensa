// Selection itself is managed by dashboard.js; only card-specific behavior lives here.
let cardLogoPreviewUrl = null;
function clearLogoPreviewUrl() {
  if (cardLogoPreviewUrl) URL.revokeObjectURL(cardLogoPreviewUrl);
  cardLogoPreviewUrl = null;
}

function validateWatermark(form) {
  if (!form) return;
  const hasLogo = form.elements.logo.files.length > 0 || (
    form.querySelector('[data-saved-logo]').dataset.savedLogo === 'true' &&
    form.elements.remove_logo.value !== 'true'
  );
  const hasName = Boolean(form.elements.school_name.value.trim());
  form.elements.school_name.setCustomValidity(hasLogo !== hasName
    ? 'Isi nama sekolah dan logo bersama-sama, atau kosongkan keduanya.' : '');
}

document.addEventListener('click', (event) => {
  const form = event.target.closest('[data-card-settings]');
  if (!form) return;
  if (event.target.closest('[data-logo-upload]')) form.elements.logo.click();
  if (event.target.closest('[data-watermark-clear]')) {
    form.elements.school_name.value = '';
    clearLogoPreviewUrl();
    form.elements.logo.value = '';
    form.elements.remove_logo.value = 'true';
    form.querySelector('[data-logo-preview]').hidden = true;
    form.querySelector('[data-logo-preview]').removeAttribute('src');
    form.querySelector('[data-logo-empty]').hidden = false;
    form.querySelector('[data-logo-delete]').hidden = true;
    form.querySelector('[data-watermark-clear]').hidden = true;
    validateWatermark(form);
    return;
  }
  if (event.target.closest('[data-logo-delete]')) {
    clearLogoPreviewUrl();
    form.elements.logo.value = '';
    form.elements.remove_logo.value = 'true';
    form.querySelector('[data-logo-preview]').hidden = true;
    form.querySelector('[data-logo-preview]').removeAttribute('src');
    form.querySelector('[data-logo-empty]').hidden = false;
    form.querySelector('[data-logo-delete]').hidden = true;
    form.querySelector('[data-watermark-clear]').hidden = !form.elements.school_name.value.trim();
    validateWatermark(form);
  }
});

document.addEventListener('change', (event) => {
  const form = event.target.closest('[data-card-settings]');
  if (!form || event.target.name !== 'logo') return;
  clearLogoPreviewUrl();
  const file = form.elements.logo.files[0];
  if (file) {
    cardLogoPreviewUrl = URL.createObjectURL(file);
    form.querySelector('[data-logo-preview]').src = cardLogoPreviewUrl;
    form.querySelector('[data-logo-preview]').hidden = false;
    form.querySelector('[data-logo-empty]').hidden = true;
    form.querySelector('[data-logo-delete]').hidden = false;
    form.querySelector('[data-watermark-clear]').hidden = false;
    form.elements.remove_logo.value = 'false';
  }
  validateWatermark(form);
});

document.addEventListener('htmx:beforeSwap', event => {
  if (event.detail.target?.id === 'modal-content') clearLogoPreviewUrl();
});
document.getElementById('student-modal')?.addEventListener('close', clearLogoPreviewUrl);
document.addEventListener('htmx:afterSwap', () => validateWatermark(document.querySelector('[data-card-settings]')));
document.addEventListener('DOMContentLoaded', () => validateWatermark(document.querySelector('[data-card-settings]')));
document.addEventListener('input', (event) => {
  const form = event.target.closest('[data-card-settings]');
  if (form && event.target.name === 'school_name') validateWatermark(form);
  if (!form || !['width_mm', 'height_mm'].includes(event.target.name)) return;
  const value = Number(event.target.value);
  if (!Number.isFinite(value) || value <= 0) return;
  const widthChanged = event.target.name === 'width_mm';
  form.elements.dimension_source.value = widthChanged ? 'width' : 'height';
  form.elements[widthChanged ? 'height_mm' : 'width_mm'].value = Number((value * (widthChanged ? 8 / 5 : 5 / 8)).toFixed(3));
});

function updateCardActions() {
  const form = document.querySelector('[data-card-operation]');
  if (!form) return;
  const scope = form.elements.scope.value;
  const selected = selectedTableIds(document.querySelector('#student-results')).length;
  const empty = scope === 'selected' ? !selected : scope === 'page' && !form.querySelector('[name="page_ids"]');
  form.querySelectorAll('button[type="submit"]').forEach(button => { button.disabled = empty; });
  form.querySelector('[data-card-status]').textContent = scope === 'selected'
    ? `${selected} siswa dipilih. Hasil dibuka di tab baru.`
    : 'Hasil dibuka di tab baru. Beberapa kartu diunduh sebagai ZIP.';
}

document.addEventListener('change', updateCardActions);
document.addEventListener('tableSelectionChanged', updateCardActions);
document.addEventListener('htmx:afterSwap', updateCardActions);
document.addEventListener('DOMContentLoaded', updateCardActions);
document.addEventListener('submit', (event) => {
  const form = event.target.closest('[data-card-operation]');
  if (!form) return;
  form.querySelectorAll('[data-card-selected]').forEach(input => input.remove());
  const selected = selectedTableIds(document.querySelector('#student-results'));
  if (form.elements.scope.value === 'selected' && !selected.length) {
    event.preventDefault();
    updateCardActions();
    return;
  }
  form.elements.confirmed.value = 'false';
  if (form.elements.scope.value === 'all') {
    if (!window.confirm('Proses SEMUA siswa di database, termasuk yang tidak tampil pada filter saat ini? Operasi ini dapat menggunakan banyak sumber daya dan memerlukan waktu lama. Gunakan hanya bila diperlukan.')) {
      event.preventDefault();
      return;
    }
    form.elements.confirmed.value = 'true';
  }
  selected.forEach(id => {
    const input = document.createElement('input');
    input.type = 'hidden'; input.name = 'ids'; input.value = id;
    input.dataset.cardSelected = '';
    form.append(input);
  });
});
