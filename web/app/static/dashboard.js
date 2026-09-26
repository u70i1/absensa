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

function updateTableSelection(section) {
  const boxes = [...section.querySelectorAll('.row-selection')];
  const count = boxes.filter((box) => box.checked).length;
  const all = section.querySelector('[data-select-all]');
  all.checked = count > 0 && count === boxes.length;
  all.indeterminate = count > 0 && count < boxes.length;
  all.disabled = !boxes.length;
  section.querySelector('[data-selection-count]').textContent = `${count} dipilih`;
  section.querySelectorAll('.selection-toolbar button').forEach((button) => { button.disabled = !count; });
  boxes.forEach((box) => box.closest('tr').classList.toggle('is-selected', box.checked));
}

document.addEventListener('click', (event) => {
  const toggle = event.target.closest('[data-selection-toggle]');
  if (!toggle) return;
  const section = toggle.closest('[data-table-selection]');
  const active = section.classList.toggle('is-selecting');
  toggle.setAttribute('aria-pressed', String(active));
  toggle.textContent = active ? 'Selesai' : 'Pilih';
  section.querySelector('.selection-toolbar').hidden = !active;
  section.querySelectorAll('.selection-cell').forEach((cell) => { cell.hidden = !active; });
  section.querySelectorAll('tr.empty-row td, tr.class-empty-row td').forEach((cell) => {
    cell.colSpan = section.querySelectorAll('thead th:not([hidden])').length;
  });
  section.querySelectorAll('.row-selection').forEach((box) => {
    box.checked = false;
  });
  updateTableSelection(section);
});

document.addEventListener('change', (event) => {
  const section = event.target.closest('[data-table-selection]');
  if (!section) return;
  if (event.target.matches('[data-select-all]')) {
    section.querySelectorAll('.row-selection').forEach((box) => { box.checked = event.target.checked; });
  }
  if (event.target.matches('[data-select-all], .row-selection')) updateTableSelection(section);
});

// Capture row clicks before HTMX detail buttons or class links navigate away.
document.addEventListener('click', (event) => {
  const row = event.target.closest('.is-selecting .student-row, .is-selecting .class-row');
  if (!row || event.target.closest('.row-selection, .row-actions') || window.getSelection()?.toString()) return;
  event.preventDefault();
  event.stopPropagation();
  const box = row.querySelector('.row-selection');
  box.checked = !box.checked;
  updateTableSelection(row.closest('[data-table-selection]'));
}, true);

// Do not restore stale selected IDs from an HTMX history snapshot.
document.addEventListener('htmx:beforeHistorySave', () => {
  document.querySelectorAll('.is-selecting [data-selection-toggle]').forEach((toggle) => toggle.click());
});
