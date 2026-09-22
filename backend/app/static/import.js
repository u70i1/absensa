document.querySelectorAll("[data-import-upload]").forEach((form) => {
  const input = form.querySelector('input[type="file"]');
  const error = form.querySelector("[data-file-error]");
  const submit = form.querySelector('button[type="submit"]');
  input.addEventListener("change", () => {
    const file = input.files[0];
    let message = "";
    const name = file?.name.toLowerCase() || "";
    const excel = name.endsWith(".xlsx");
    const archive = /\.(zip|rar|7z|tar|tar\.gz|tgz|tar\.bz2|tbz2|tar\.xz|txz)$/.test(name);
    if (file && !excel && !archive) message = "Pilih Excel, ZIP, RAR, 7z, TAR, atau TAR terkompresi.";
    if (file && file.size > (excel ? 10 : 100) * 1024 * 1024) message = "Excel maksimal 10 MB; arsip maksimal 100 MB.";
    input.setCustomValidity(message);
    error.textContent = message;
    error.hidden = !message;
    form.querySelector("[data-file-name]").textContent = file?.name || "Pilih file Excel atau arsip";
    form.querySelector("[data-file-size]").textContent = file ? `Siap diperiksa · ${Math.max(1, Math.ceil(file.size / 1024))} KB` : "Excel maksimal 10 MB · Arsip 100 MB";
  });
  form.addEventListener("submit", () => {
    document.querySelectorAll("[data-import-upload] button[type='submit']").forEach((button) => { button.disabled = true; });
    submit.textContent = "Memeriksa file…";
  });
});

const confirmation = document.getElementById("import-confirm");
if (confirmation) {
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

if (window.location.hash === "#import-review") document.getElementById("import-review")?.focus();
window.addEventListener("pageshow", (event) => {
  // Restore button states after navigating back to a submitted form.
  if (event.persisted) window.location.reload();
});
