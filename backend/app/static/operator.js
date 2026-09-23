document.addEventListener('htmx:beforeSwap', (event) => {
  if (event.detail.xhr.getResponseHeader('X-Operator-Fragment') === 'scan') {
    event.detail.shouldSwap = true;
    event.detail.isError = false;
  }
});
document.addEventListener('htmx:afterSwap', (event) => {
  if (event.detail.target?.id === 'operator-feed') {
    const input = document.getElementById('scan-nisn');
    if (document.getElementById('operator-feed').dataset.scanSucceeded === 'true') input.value = '';
    input.focus();
    if (input.value) input.select();
  }
});
