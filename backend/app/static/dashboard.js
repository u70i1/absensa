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
  if (["student-results", "class-results"].includes(event.detail.target?.id)) {
    document
      .querySelector("#student-results .table-container, #class-results .table-container")
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
document.addEventListener("classSaved", () => {
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
  if (event.detail.successful) {
    photoUploadStatus(event, "Foto berhasil diunggah.");
  }
});

document.addEventListener("htmx:responseError", (event) => {
  if (
    photoUploadStatus(
      event,
      event.detail.xhr.status === 404 || event.detail.xhr.status === 501
        ? "Unggah foto belum tersedia. Perubahan data siswa tetap dapat disimpan."
        : "Foto gagal diunggah. Silakan coba lagi.",
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
