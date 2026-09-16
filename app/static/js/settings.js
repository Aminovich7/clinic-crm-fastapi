(async function () {
  const user = await initPage({ allowedRoles: ["superadmin"] });
  if (!user) return;

  const errorContainer = document.getElementById("error-container");
  const successContainer = document.getElementById("success-container");
  const input = document.getElementById("default_minus_beshming");
  const meta = document.getElementById("settings-meta");

  function clearMessages() {
    errorContainer.innerHTML = "";
    successContainer.innerHTML = "";
  }

  function showSuccess(message) {
    successContainer.innerHTML = "";
    const box = document.createElement("div");
    box.className = "success-box";
    box.textContent = message;
    successContainer.appendChild(box);
  }

  attachMoneyInput(input);

  async function loadSettings() {
    clearMessages();
    try {
      const data = await apiFetch("/admin/settings/finance");
      input.value = formatMoneyInputValue(data.default_minus_beshming);
      meta.textContent = `Oxirgi yangilanish: ${formatDateTime(data.updated_at)}`;
    } catch (err) {
      showError(errorContainer, err.detail || err.message || "Sozlamalarni yuklashda xatolik");
    }
  }

  document.getElementById("settings-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    clearMessages();
    try {
      const data = await apiFetch("/admin/settings/finance", {
        method: "PATCH",
        body: { default_minus_beshming: moneyInputValue(input) },
      });
      input.value = formatMoneyInputValue(data.default_minus_beshming);
      meta.textContent = `Oxirgi yangilanish: ${formatDateTime(data.updated_at)}`;
      showSuccess("Sozlamalar yangilandi");
    } catch (err) {
      showError(errorContainer, err.detail || err.message || "Sozlamalarni yangilashda xatolik");
    }
  });

  loadSettings();
})();
