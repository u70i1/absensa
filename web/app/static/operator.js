// Milliseconds after a successful scan before the card-printing sound plays.
const PRINT_SOUND_DELAY = 0;

const scanForm = document.querySelector('.scanner-form');

if (scanForm) {
  const input = scanForm.querySelector('#scan-nisn');
  const stage = document.getElementById('scan-card-stage');
  const successAudio = document.querySelector('[data-scan-success-audio]');
  const errorAudio = document.querySelector('[data-scan-error-audio]');
  const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
  let submitting = false;
  let cardQueue = Promise.resolve();
  let previousHistory = new Map();
  let previousScroll = 0;
  let printSoundTimer;
  let printSoundGeneration = 0;

  // Fetch once on page load; scans play the page-local audio instead of its URL.
  const printSoundReady = successAudio?.dataset.source
    ? fetch(successAudio.dataset.source, { cache: 'force-cache' })
      .then((response) => {
        if (!response.ok) throw new Error('Print sound unavailable');
        return response.blob();
      })
      .then((blob) => {
        successAudio.src = URL.createObjectURL(blob);
        successAudio.load();
      })
      .catch(() => {
        successAudio.src = successAudio.dataset.source;
        successAudio.load();
      })
    : Promise.resolve();

  function play(audio) {
    if (!audio) return;
    audio.currentTime = 0;
    audio.play().catch(() => {});
  }

  function cancelPrintSound() {
    window.clearTimeout(printSoundTimer);
    printSoundGeneration += 1;
  }

  function playPrintSoundLater() {
    cancelPrintSound();
    const generation = printSoundGeneration;
    printSoundTimer = window.setTimeout(async () => {
      printSoundTimer = undefined;
      await printSoundReady;
      if (generation === printSoundGeneration) play(successAudio);
    }, PRINT_SOUND_DELAY);
  }

  input.addEventListener('keydown', (event) => {
    if (submitting && event.key === 'Enter') { event.preventDefault(); return; }
  });
  input.addEventListener('invalid', () => {
    cancelPrintSound();
    play(errorAudio);
  });

  scanForm.addEventListener('submit', (event) => {
    if (submitting) { event.preventDefault(); return; }
    cancelPrintSound();
    submitting = true;
    input.readOnly = true;
  });

  function animateCard(card, className) {
    if (reducedMotion.matches) return Promise.resolve();
    return new Promise((resolve) => {
      const finish = (event) => {
        if (event && event.target !== card) return;
        card.removeEventListener('animationend', finish);
        card.removeEventListener('animationcancel', finish);
        resolve();
      };
      card.addEventListener('animationend', finish);
      card.addEventListener('animationcancel', finish);
      card.classList.add(className);
    });
  }

  function showCard(template) {
    const content = template.content.cloneNode(true);
    cardQueue = cardQueue.then(async () => {
      const next = content.querySelector('.scanned-student-card');
      if (!next) return;
      const current = stage.querySelector('.scanned-student-card');
      stage.querySelector('.scan-stage-empty')?.remove();
      stage.append(next);
      const exiting = current ? animateCard(current, 'scan-card-exit') : Promise.resolve();
      const entering = animateCard(next, 'scan-card-enter');
      await Promise.all([exiting, entering]);
      current?.remove();
      next.classList.remove('scan-card-enter');
    });
  }

  document.addEventListener('htmx:beforeSwap', (event) => {
    if (event.detail.xhr.getResponseHeader('X-Operator-Fragment') === 'scan') {
      event.detail.shouldSwap = true;
      event.detail.isError = false;
    }
    if (event.detail.target?.id !== 'recent-scans') return;
    const list = event.detail.target.querySelector('.recent-list');
    previousScroll = list?.scrollTop || 0;
    previousHistory = new Map([...event.detail.target.querySelectorAll('[data-scan-id]')]
      .map((row) => [row.dataset.scanId, row.getBoundingClientRect().top]));
  });

  document.addEventListener('htmx:afterSwap', (event) => {
    if (event.detail.target?.id === 'scan-feedback') {
      const feedback = document.getElementById('scan-feedback');
      const succeeded = feedback.dataset.scanSucceeded === 'true';
      submitting = false;
      input.readOnly = false;
      if (succeeded) {
        input.value = '';
        playPrintSoundLater();
        const template = feedback.querySelector('[data-scan-card]');
        if (template) showCard(template);
        const recent = document.getElementById('recent-scans');
        if (recent) htmx.trigger(recent, 'scanRecorded');
      } else if (feedback.querySelector('[role="alert"]')) {
        play(errorAudio);
      }
      input.focus();
      if (!succeeded && input.value) input.select();
      input.dispatchEvent(new Event('select'));
    }
    if (event.detail.target?.id !== 'recent-scans') return;
    const current = document.getElementById('recent-scans');
    const list = current.querySelector('.recent-list');
    const rows = [...current.querySelectorAll('[data-scan-id]')];
    if (!list) return;
    list.scrollTop = previousScroll;
    const added = rows.filter((row) => !previousHistory.has(row.dataset.scanId));
    if (!reducedMotion.matches) {
      rows.forEach((row) => {
        const oldTop = previousHistory.get(row.dataset.scanId);
        const offset = oldTop === undefined
          ? -row.getBoundingClientRect().height
          : oldTop - row.getBoundingClientRect().top;
        if (offset) {
          row.style.setProperty('--recent-offset', `${offset}px`);
          row.style.setProperty('--recent-start-opacity', oldTop === undefined ? '0' : '1');
          row.classList.add('recent-item-moving');
          row.addEventListener('animationend', () => {
            row.classList.remove('recent-item-moving');
            row.style.removeProperty('--recent-offset');
            row.style.removeProperty('--recent-start-opacity');
          }, { once: true });
        }
      });
    }
    if (added.length) list.scrollTo({ top: 0, behavior: reducedMotion.matches ? 'auto' : 'smooth' });
  });

  document.addEventListener('htmx:afterRequest', (event) => {
    if (event.detail.elt !== scanForm) return;
    submitting = false;
    input.readOnly = false;
  });

  document.addEventListener('htmx:responseError', (event) => {
    if (event.detail.elt !== scanForm || event.detail.xhr.getResponseHeader('X-Operator-Fragment') === 'scan') return;
    play(errorAudio);
    input.focus();
    input.select();
  });

  document.addEventListener('error', (event) => {
    if (!event.target.matches?.('[data-avatar-photo]')) return;
    const avatar = event.target.closest('[data-avatar-fallback]');
    avatar.textContent = avatar.dataset.avatarFallback;
  }, true);
}
