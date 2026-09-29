// Keep one real form value for each code; visual slots are decorative only.
document.querySelectorAll('.otp-code').forEach((input) => {
  const length = input.maxLength;
  const form = input.form;
  const slots = [...input.parentElement.querySelectorAll('.otp-slots span')];

  function renderSlots() {
    if (!slots.length) return;
    const active = Math.min(input.selectionStart || 0, length - 1);
    slots.forEach((slot, index) => {
      slot.textContent = input.value[index] || '';
      slot.classList.toggle('otp-active', document.activeElement === input && index === active);
    });
  }

  input.addEventListener('input', () => {
    const position = input.selectionStart || 0;
    const before = input.value.slice(0, position).replace(/[^0-9]/g, '');
    input.value = input.value.replace(/[^0-9]/g, '').slice(0, length);
    input.setSelectionRange(before.length, before.length);
    renderSlots();
    if (input.value.length === length && !input.readOnly && !input.disabled) form.requestSubmit();
  });

  input.addEventListener('keydown', (event) => {
    if (/^[0-9]$/.test(event.key) && !event.ctrlKey && !event.metaKey) {
      const position = input.selectionStart;
      if (position === input.selectionEnd && position < input.value.length) {
        input.setSelectionRange(position, position + 1);
      }
    } else if (event.key.length === 1 && !event.ctrlKey && !event.metaKey && !event.altKey) {
      event.preventDefault();
    }
  });

  input.addEventListener('paste', (event) => {
    event.preventDefault();
    const digits = event.clipboardData.getData('text').replace(/[^0-9]/g, '').slice(0, length);
    if (!digits) return;
    if (digits.length === length) {
      input.value = digits;
      input.setSelectionRange(length, length);
    } else {
      input.setRangeText(digits, input.selectionStart, input.selectionEnd, 'end');
    }
    input.dispatchEvent(new Event('input', { bubbles: true }));
  });

  if (slots.length) {
    input.parentElement.classList.add('otp-enhanced');
    input.addEventListener('click', (event) => {
      const clicked = slots.findIndex((slot) => event.clientX <= slot.getBoundingClientRect().right);
      const index = clicked < 0 ? slots.length - 1 : clicked;
      const position = Math.min(index, input.value.length);
      input.setSelectionRange(position, Math.min(position + 1, input.value.length));
      renderSlots();
    });
    ['focus', 'blur', 'keyup', 'select'].forEach((name) => input.addEventListener(name, renderSlots));
    renderSlots();
  }
});
