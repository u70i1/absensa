document.querySelectorAll("[data-import-upload]").forEach((form) => {
  const input = form.querySelector('input[type="file"]');
  const error = form.querySelector("[data-file-error]");
  const submit = form.querySelector('button[type="submit"]');
  const dropzone = form.querySelector("[data-file-dropzone]");
  let uploading = false;
  const showError = (message) => {
    error.textContent = message;
    error.hidden = !message;
  };
  input.addEventListener("change", () => {
    const file = input.files[0];
    let message = "";
    const name = file?.name.toLowerCase() || "";
    const excel = name.endsWith(".xlsx");
    const archive = /\.(zip|rar|7z|tar|tar\.gz|tgz|tar\.bz2|tbz2|tar\.xz|txz)$/.test(name);
    if (file && !excel && !archive) message = "Pilih Excel, ZIP, RAR, 7z, TAR, atau TAR terkompresi.";
    if (file && file.size > (excel ? 10 : 100) * 1024 * 1024) message = "Excel maksimal 10 MB; arsip maksimal 100 MB.";
    input.setCustomValidity(message);
    showError(message);
    form.querySelector("[data-file-name]").textContent = file?.name || "Pilih file Excel atau arsip";
    form.querySelector("[data-file-size]").textContent = file ? `Siap diperiksa · ${Math.max(1, Math.ceil(file.size / 1024))} KB` : "Excel maksimal 10 MB · Arsip 100 MB";
  });
  const isFileDrag = (event) => Array.from(event.dataTransfer?.types || []).includes("Files");
  dropzone.addEventListener("dragover", (event) => {
    if (!isFileDrag(event)) return;
    event.preventDefault();
    const available = !input.disabled && !uploading;
    event.dataTransfer.dropEffect = available ? "copy" : "none";
    dropzone.classList.toggle("is-dragging", available);
  });
  dropzone.addEventListener("dragleave", (event) => {
    if (!dropzone.contains(event.relatedTarget)) dropzone.classList.remove("is-dragging");
  });
  dropzone.addEventListener("drop", (event) => {
    event.preventDefault();
    dropzone.classList.remove("is-dragging");
    if (input.disabled || uploading) return;
    const files = event.dataTransfer?.files;
    const items = Array.from(event.dataTransfer?.items || []);
    if (items.some((item) => item.webkitGetAsEntry?.()?.isDirectory)) {
      showError("Unggah folder sebagai satu file arsip terlebih dahulu.");
      return;
    }
    if (!files?.length) return;
    if (files.length !== 1) {
      showError("Pilih satu file saja. Gabungkan beberapa file dalam satu arsip.");
      return;
    }
    input.files = files;
    input.dispatchEvent(new Event("change", { bubbles: true }));
    if (input.checkValidity()) form.requestSubmit();
  });
  form.addEventListener("submit", () => {
    uploading = true;
    document.querySelectorAll("[data-import-upload] button[type='submit']").forEach((button) => { button.disabled = true; });
    submit.textContent = "Memeriksa file…";
  });
});

function bindImportConfirmation() {
  const confirmation = document.getElementById("import-confirm");
  if (!confirmation || confirmation.dataset.bound) return;
  confirmation.dataset.bound = "true";
  const submit = document.querySelector("[data-confirm-import]");
  confirmation.addEventListener("change", () => {
    const counts = { create: 0, update: 0 };
    confirmation.querySelectorAll("[data-import-row]").forEach((row) => {
      const checked = row.querySelector("input").checked;
      if (checked) counts[row.dataset.action]++;
      row.querySelector("[data-row-toggle]").textContent = checked ? "Batalkan" : "Dibatalkan";
    });
    Object.entries(counts).forEach(([action, count]) => { document.querySelector(`[data-count="${action}"]`).textContent = count; });
    submit.disabled = counts.create + counts.update === 0;
  });
  confirmation.addEventListener("submit", () => {
    submit.disabled = true;
    submit.textContent = "Menyimpan…";
  });
  confirmation.dispatchEvent(new Event("change"));
}

bindImportConfirmation();
// Delegate so refreshed preview rows behave the same after saving an edit.
document.addEventListener("click", (event) => {
  if (event.defaultPrevented || event.target.closest("[data-import-actions], a, button, input, label, select, textarea")) return;
  const row = event.target.closest("[data-import-row]");
  if (!row || window.getSelection()?.toString()) return;
  row.focus({ preventScroll: true });
  htmx.trigger(row, "editImportRow");
});
document.addEventListener("keydown", (event) => {
  if (event.defaultPrevented || !event.target.matches("[data-import-row]")) return;
  if (event.key !== "Enter" && event.key !== " ") return;
  event.preventDefault();
  if (!event.repeat) htmx.trigger(event.target, "editImportRow");
});
document.addEventListener("htmx:afterSwap", bindImportConfirmation);
document.addEventListener("importRowSaved", () => {
  document.querySelector("#student-modal [data-close-modal]")?.click();
  document.getElementById("import-review")?.focus();
});

if (window.location.hash === "#import-review") document.getElementById("import-review")?.focus();
window.addEventListener("pageshow", (event) => {
  // Restore button states after navigating back to a submitted form.
  if (event.persisted) window.location.reload();
});
