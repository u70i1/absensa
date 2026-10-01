// Selection itself is managed by dashboard.js; only card-specific behavior lives here.
let cardLogoPreviewUrl = null;
let cardSettingsPreviewTimer = null;
let cardSettingsPreviewRequest = null;

function clearSettingsPreview() {
  clearTimeout(cardSettingsPreviewTimer);
  cardSettingsPreviewTimer = null;
  cardSettingsPreviewRequest?.abort();
  cardSettingsPreviewRequest = null;
}

function syncCardMeasureSliders(form) {
  form?.querySelectorAll('[data-card-measure]').forEach(slider => {
    const value = form.elements[slider.dataset.cardMeasure].valueAsNumber;
    if (Number.isFinite(value)) slider.value = value;
  });
}

function queueSettingsPreview(form) {
  if (!form) return;
  clearSettingsPreview();
  const layout = form.closest('.card-settings-layout');
  const status = layout.querySelector('[data-preview-status]');
  const fields = ['width_mm', 'height_mm', 'gap_mm', 'photo_ratio_width', 'photo_ratio_height'];
  if (fields.some(name => !form.elements[name].checkValidity())) {
    status.textContent = 'Periksa ukuran dan rasio foto untuk memperbarui pratinjau.';
    return;
  }
  const width = form.elements.width_mm.valueAsNumber;
  const height = form.elements.height_mm.valueAsNumber;
  const gap = form.elements.gap_mm.valueAsNumber;
  layout.querySelector('[data-settings-preview]').style.width = `${width * 2.4}px`;
  layout.querySelector('[data-preview-dimensions]').textContent = `${width} × ${height} mm`;
  layout.querySelector('[data-preview-gap]').textContent = `Jarak antarkartu: ${gap} mm`;
  cardSettingsPreviewTimer = setTimeout(async () => {
    const controller = new AbortController();
    cardSettingsPreviewRequest = controller;
    status.textContent = 'Memperbarui pratinjau…';
    try {
      const response = await fetch(form.dataset.previewUrl, {
        method: 'POST', body: new FormData(form), signal: controller.signal,
      });
      if (!response.ok) throw new Error('Preview failed');
      const preview = await response.json();
      if (controller.signal.aborted || !form.isConnected) return;
      layout.querySelector('[data-settings-preview]').src = preview.uri;
      status.textContent = '';
    } catch (error) {
      if (error.name !== 'AbortError' && form.isConnected) {
        status.textContent = 'Pratinjau gagal diperbarui. Periksa pengaturan lalu coba lagi.';
      }
    } finally {
      if (cardSettingsPreviewRequest === controller) cardSettingsPreviewRequest = null;
    }
  }, 200);
}

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

function validatePhotoRatio(form) {
  if (!form) return;
  ['photo_ratio_width', 'photo_ratio_height'].forEach(name => {
    const input = form.elements[name];
    const value = input.valueAsNumber;
    input.setCustomValidity(Number.isFinite(value) && value > 0
      ? '' : 'Rasio foto harus berupa angka positif. Boleh menggunakan desimal.');
  });
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
    queueSettingsPreview(form);
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
    queueSettingsPreview(form);
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
  queueSettingsPreview(form);
});

document.addEventListener('htmx:beforeSwap', event => {
  if (event.detail.target?.id === 'modal-content') {
    clearLogoPreviewUrl();
    clearSettingsPreview();
  }
});
document.getElementById('student-modal')?.addEventListener('close', () => {
  clearLogoPreviewUrl();
  clearSettingsPreview();
});
function validateCardSettings() {
  const form = document.querySelector('[data-card-settings]');
  validateWatermark(form);
  validatePhotoRatio(form);
  syncCardMeasureSliders(form);
}
document.addEventListener('htmx:afterSwap', validateCardSettings);
document.addEventListener('DOMContentLoaded', validateCardSettings);
document.addEventListener('input', (event) => {
  const form = event.target.closest('[data-card-settings]');
  if (!form) return;
  const name = event.target.dataset.cardMeasure || event.target.name;
  if (event.target.dataset.cardMeasure) form.elements[name].value = event.target.value;
  if (name === 'school_name') validateWatermark(form);
  if (['photo_ratio_width', 'photo_ratio_height'].includes(name)) validatePhotoRatio(form);
  if (['width_mm', 'height_mm'].includes(name)) {
    const value = form.elements[name].valueAsNumber;
    if (Number.isFinite(value) && value > 0) {
      const widthChanged = name === 'width_mm';
      form.elements.dimension_source.value = widthChanged ? 'width' : 'height';
      form.elements[widthChanged ? 'height_mm' : 'width_mm'].value = Number((value * (widthChanged ? 8 / 5 : 5 / 8)).toFixed(3));
    }
  }
  syncCardMeasureSliders(form);
  if (name !== 'logo') queueSettingsPreview(form);
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
