const modal = document.getElementById("student-modal");
let modalOpener = null;

function closeModal() {
  if (!modal.open) {
    window.location.assign(document.querySelector("[data-dashboard-home]")?.dataset.dashboardHome || "/admin/students");
    return;
  }
  if (modal.classList.contains("is-closing")) return;
  if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
    modal.close();
    return;
  }
  modal.classList.add("is-closing");
  const animations = modal
    .getAnimations()
    .map((animation) => animation.finished);
  Promise.allSettled(animations).then(() => {
    modal.close();
    modal.classList.remove("is-closing");
  });
}

modal.addEventListener("cancel", (event) => {
  event.preventDefault();
  closeModal();
});

modal.addEventListener("keydown", (event) => {
  if (event.key !== "Tab") return;
  const controls = [
    ...modal.querySelectorAll(
      "button:not(:disabled), input:not(:disabled), select:not(:disabled), a[href], [tabindex='0']",
    ),
  ].filter((element) => element.getClientRects().length);
  const first = controls[0];
  const last = controls.at(-1);
  if (
    event.shiftKey &&
    (document.activeElement === first ||
      !controls.includes(document.activeElement))
  ) {
    event.preventDefault();
    last?.focus();
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault();
    first?.focus();
  }
});

document.addEventListener("click", (event) => {
  if (event.target.closest("[data-close-modal]")) closeModal();
});

// Delegate to the real link so rows replaced by HTMX remain clickable.
document.addEventListener("click", (event) => {
  if (event.defaultPrevented || event.target.closest("a, button, input, select, textarea")) return;
  const row = event.target.closest(".class-row");
  if (!row || window.getSelection()?.toString()) return;
  row.querySelector(".class-students-link")?.click();
});

modal.addEventListener("click", (event) => {
  const bounds = modal.getBoundingClientRect();
  if (
    event.target === modal &&
    (event.clientX < bounds.left ||
      event.clientX > bounds.right ||
      event.clientY < bounds.top ||
      event.clientY > bounds.bottom)
  )
    closeModal();
});

modal.addEventListener("close", () => {
  document.getElementById("modal-content").replaceChildren();
  if (modalOpener?.isConnected) modalOpener.focus();
  else document.querySelector("#add-student, #add-class")?.focus();
  modalOpener = null;
});

document.addEventListener("htmx:beforeRequest", (event) => {
  document.getElementById("request-error").hidden = true;
  if (event.detail.target?.id === "modal-content" && !modal.open) {
    modalOpener = document.activeElement;
  }
});

document.addEventListener("htmx:beforeSwap", (event) => {
  const { xhr } = event.detail;
  // Expected error responses retain their HTTP status and carry rendered UI.
  if (xhr.getResponseHeader("X-Admin-Fragment") === "modal") {
    event.detail.shouldSwap = true;
    event.detail.isError = false;
  }
});

document.addEventListener("htmx:afterSwap", (event) => {
  if (["student-results", "class-results", "scan-results"].includes(event.detail.target?.id)) {
    document
      .querySelector("#student-results .table-container, #class-results .table-container, #scan-results .table-container")
      ?.classList.add("interaction-feedback");
    return;
  }
  if (event.detail.target?.id !== "modal-content") return;
  if (!modal.open) modal.showModal();
  else if (!modal.classList.contains("is-closing")) {
    // A fresh child also animates repeated swaps (e.g. detail → edit → validation).
    document
      .querySelector("#modal-content > :first-child")
      ?.classList.add("interaction-feedback");
  }
  const focusTarget =
    modal.querySelector("[aria-invalid='true'], [autofocus]") ||
    modal.querySelector("#modal-title");
  focusTarget?.focus();
});

document.addEventListener("studentSaved", () => {
  if (modal.open) closeModal();
});
document.addEventListener("accessSaved", () => { if (modal.open) closeModal(); });
document.addEventListener("classSaved", () => {
  if (modal.open) closeModal();
});
document.addEventListener("scanSaved", () => {
  if (modal.open) closeModal();
});

function showRequestError(message) {
  const target = modal.open
    ? document.getElementById("modal-content")
    : document.getElementById("request-error");
  if (modal.open) {
    let alert = target.querySelector(".request-failure");
    if (!alert) {
      alert = document.createElement("p");
      alert.className = "form-errors request-failure";
      alert.setAttribute("role", "alert");
      target.prepend(alert);
    }
    alert.textContent = message;
  } else {
    target.textContent = message;
    target.hidden = false;
  }
}

function photoUploadStatus(event, message, failed = false) {
  const form = event.detail.elt?.closest("[data-photo-upload]");
  if (!form) return false;
  const status = form.querySelector("#photo-status");
  status.textContent = message;
  status.className = failed ? "field-error" : "field-help";
  return true;
}

document.addEventListener("htmx:beforeRequest", (event) => {
  photoUploadStatus(event, "Mengunggah foto…");
});

document.addEventListener("htmx:afterRequest", (event) => {
  if (event.detail.successful && event.detail.elt?.closest("[data-photo-upload]")) {
    try {
      const result = JSON.parse(event.detail.xhr.responseText);
      if (!result.photo_url || !Number.isInteger(result.student_id)) throw new Error("Invalid photo response");
      document.querySelectorAll(`[data-student-avatar="${result.student_id}"]`).forEach((avatar) => {
        const image = document.createElement("img");
        image.src = result.photo_url;
        image.alt = "";
        avatar.replaceChildren(image);
      });
      photoUploadStatus(event, "Foto berhasil diunggah.");
      event.detail.elt.closest("[data-photo-upload]").reset();
    } catch {
      photoUploadStatus(event, "Foto gagal diunggah. Silakan masuk kembali lalu coba lagi.", true);
    }
  }
});

document.addEventListener("htmx:responseError", (event) => {
  let photoError = "Foto gagal diunggah. Silakan coba lagi.";
  try {
    const detail = JSON.parse(event.detail.xhr.responseText).detail;
    if (typeof detail === "string") photoError = detail;
  } catch { /* Use the fallback for non-JSON errors. */ }
  if (
    photoUploadStatus(
      event,
      photoError,
      true,
    )
  )
    return;
  showRequestError("Permintaan gagal. Silakan coba lagi.");
});
document.addEventListener("htmx:sendError", (event) => {
  if (
    photoUploadStatus(
      event,
      "Foto gagal diunggah. Periksa koneksi lalu coba lagi.",
      true,
    )
  )
    return;
  showRequestError(
    "Tidak dapat terhubung ke server. Periksa koneksi lalu coba lagi.",
  );
});

// Keep selection outside swapped HTML so filters, pages, and history retain it.
// Each dashboard has its own state, including separate student and card selections.
const tableSelections = new Map();

function tableSelectionState(section) {
  const key = section.dataset.tableSelection || section.id;
  if (!tableSelections.has(key)) {
    tableSelections.set(key, { active: false, ids: new Set(), cardScope: 'page' });
  }
  return tableSelections.get(key);
}

function selectedTableIds(section) {
  return section ? [...tableSelectionState(section).ids] : [];
}

function updateTableSelection(section) {
  const state = tableSelectionState(section);
  const boxes = [...section.querySelectorAll('.row-selection')];
  const visibleIds = new Set(boxes.map(box => box.value));
  const toggle = section.querySelector('[data-selection-toggle]');
  section.classList.toggle('is-selecting', state.active);
  toggle.setAttribute('aria-pressed', String(state.active));
  toggle.textContent = state.active ? 'Selesai' : 'Pilih';
  const form = section.querySelector('.selection-toolbar');
  form.hidden = !state.active;
  section.querySelectorAll('.selection-cell').forEach(cell => { cell.hidden = !state.active; });
  section.querySelectorAll('tr.empty-row td, tr.class-empty-row td').forEach(cell => {
    cell.colSpan = section.querySelectorAll('thead th:not([hidden])').length;
  });
  boxes.forEach(box => {
    box.checked = state.ids.has(box.value);
    box.closest('tr').classList.toggle('is-selected', box.checked);
  });
  const visibleCount = boxes.filter(box => box.checked).length;
  const all = section.querySelector('[data-select-all]');
  all.checked = visibleCount > 0 && visibleCount === boxes.length;
  all.indeterminate = visibleCount > 0 && visibleCount < boxes.length;
  all.disabled = !boxes.length;
  const hiddenCount = state.ids.size - visibleCount;
  section.querySelector('[data-selection-count]').textContent =
    `${state.ids.size} dipilih${hiddenCount ? ` · ${hiddenCount} di luar tampilan ini` : ''}`;
  form.querySelectorAll('button').forEach(button => { button.disabled = !state.ids.size; });

  // Visible checkboxes belong to this form already. Add hidden selected rows
  // explicitly, so confirmation and bulk mutations receive the whole selection.
  form.querySelectorAll('[data-selection-hidden]').forEach(input => input.remove());
  state.ids.forEach(id => {
    if (visibleIds.has(id)) return;
    const input = document.createElement('input');
    input.type = 'hidden'; input.name = 'ids'; input.value = id;
    input.dataset.selectionHidden = '';
    form.append(input);
  });
  const scope = section.querySelector('[data-card-operation] [name="scope"]');
  if (scope) scope.value = state.cardScope;
  section.dispatchEvent(new CustomEvent('tableSelectionChanged', { bubbles: true }));
}

function restoreTableSelections() {
  document.querySelectorAll('[data-table-selection]').forEach(updateTableSelection);
}

document.addEventListener('DOMContentLoaded', restoreTableSelections);
document.addEventListener('htmx:afterSwap', restoreTableSelections);
document.addEventListener('htmx:historyRestore', restoreTableSelections);
window.addEventListener('pageshow', restoreTableSelections);

document.addEventListener('click', event => {
  const toggle = event.target.closest('[data-selection-toggle]');
  if (!toggle) return;
  const section = toggle.closest('[data-table-selection]');
  const state = tableSelectionState(section);
  state.active = !state.active;
  if (!state.active) state.ids.clear();
  updateTableSelection(section);
});

document.addEventListener('change', event => {
  const section = event.target.closest('[data-table-selection]');
  if (!section) return;
  const state = tableSelectionState(section);
  if (event.target.matches('[data-card-operation] [name="scope"]')) {
    state.cardScope = event.target.value;
  }
  if (!state.active) return;
  const boxes = event.target.matches('[data-select-all]')
    ? [...section.querySelectorAll('.row-selection')]
    : event.target.matches('.row-selection') ? [event.target] : [];
  boxes.forEach(box => {
    if (event.target.checked) state.ids.add(box.value);
    else state.ids.delete(box.value);
  });
  if (boxes.length || event.target.matches('[data-select-all]')) updateTableSelection(section);
});

// Capture row clicks before HTMX detail buttons or class links navigate away.
document.addEventListener('click', event => {
  const row = event.target.closest('.is-selecting .student-row, .is-selecting .class-row');
  if (!row || event.target.closest('.row-selection, .row-actions') || window.getSelection()?.toString()) return;
  event.preventDefault();
  event.stopPropagation();
  const box = row.querySelector('.row-selection');
  const section = row.closest('[data-table-selection]');
  const state = tableSelectionState(section);
  if (state.ids.has(box.value)) state.ids.delete(box.value);
  else state.ids.add(box.value);
  updateTableSelection(section);
}, true);

// Completed deletions cannot remain selectable. Failed or canceled operations
// retain the selection, and successful edits/deactivations keep it as well.
document.addEventListener('htmx:afterRequest', event => {
  if (!event.detail.successful || event.detail.xhr.status < 200 || event.detail.xhr.status >= 300) return;
  const config = event.detail.requestConfig;
  if (!config || config.verb !== 'post') return;
  const path = new URL(config.path, location.href).pathname;
  const single = path.match(/^\/admin\/(students|classes|scans)\/(\d+)\/delete$/);
  const bulk = path.match(/^\/admin\/(students|classes|scans)\/selection\/apply$/);
  let ids, kind;
  if (single) {
    kind = single[1]; ids = [single[2]];
  } else if (bulk && config.parameters.action === 'delete') {
    kind = bulk[1];
    ids = [].concat(config.parameters.ids || []).map(String);
  } else return;
  const keys = kind === 'students' ? ['students', 'cards'] : [kind];
  keys.forEach(key => {
    const state = tableSelections.get(key);
    ids.forEach(id => state?.ids.delete(id));
  });
  restoreTableSelections();
});
