// One accessible password input is the source of truth; slots are decorative.
document.querySelectorAll('[data-pin-control]').forEach((control) => {
  const input = control.querySelector('input');
  const slots = [...control.querySelectorAll('.pin-slots span')];
  control.classList.add('pin-enhanced');
  const render = () => {
    const position = Math.min(input.selectionStart || 0, 5);
    slots.forEach((slot, i) => {
      slot.textContent = i < input.value.length ? '•' : '';
      slot.classList.toggle('pin-active', document.activeElement === input && i === position);
    });
  };
  input.addEventListener('input', () => {
    const position = input.selectionStart || 0;
    const before = input.value.slice(0, position).replace(/[^0-9]/g, '');
    input.value = input.value.replace(/[^0-9]/g, '').slice(0, 6);
    input.setSelectionRange(before.length, before.length);
    render();
  });
  input.addEventListener('keydown', (event) => {
    if (/^[0-9]$/.test(event.key) && !event.ctrlKey && !event.metaKey) {
      const position = input.selectionStart;
      if (position === input.selectionEnd && position < input.value.length) input.setSelectionRange(position, position + 1);
    } else if (event.key.length === 1 && !event.ctrlKey && !event.metaKey && !event.altKey) {
      event.preventDefault();
    }
  });
  input.addEventListener('paste', (event) => {
    event.preventDefault();
    const digits = event.clipboardData.getData('text').replace(/[^0-9]/g, '').slice(0, 6);
    if (!digits) return;
    if (digits.length === 6) {
      input.value = digits;
      input.setSelectionRange(6, 6);
    } else {
      input.setRangeText(digits, input.selectionStart, input.selectionEnd, 'end');
    }
    input.dispatchEvent(new Event('input', { bubbles: true }));
  });
  input.addEventListener('click', (event) => {
    const rect = control.getBoundingClientRect();
    const index = Math.min(input.value.length, Math.max(0, Math.min(5, Math.floor((event.clientX - rect.left) / (rect.width / 6)))));
    input.setSelectionRange(index, Math.min(index + 1, input.value.length));
    render();
  });
  ['focus', 'blur', 'keyup', 'select'].forEach((name) => input.addEventListener(name, render));
  render();
});

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
