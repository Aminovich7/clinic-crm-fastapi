(async function () {
  const user = await initPage({ allowedRoles: ["superadmin", "manager"] });
  if (!user) return;

  const errorContainer = document.getElementById("error-container");
  const successContainer = document.getElementById("success-container");
  const tbody = document.getElementById("entries-tbody");
  const pagination = document.getElementById("pagination");
  const balanceCards = document.getElementById("balance-cards");
  const entryForm = document.getElementById("entry-form");
  const dateFromInput = document.getElementById("date_from");
  const dateToInput = document.getElementById("date_to");

  attachMoneyInput(document.getElementById("medicine_cost"));
  attachMoneyInput(document.getElementById("amount_paid"));

  let page = 1;
  const pageSize = 20;

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

  function statCard(label, value, colorByValue = false) {
    const div = document.createElement("div");
    div.className = "stat-card";
    div.innerHTML = `<div class="label">${label}</div><div class="value">${formatMoney(value)}</div>`;
    if (colorByValue) {
      const valueEl = div.querySelector(".value");
      valueEl.style.color = Number(value) >= 0 ? "var(--success)" : "var(--danger)";
    }
    return div;
  }

  function currentRangeParams() {
    const params = new URLSearchParams();
    if (dateFromInput.value) params.set("date_from", dateFromInput.value);
    if (dateToInput.value) params.set("date_to", dateToInput.value);
    return params;
  }

  async function loadBalance() {
    balanceCards.innerHTML = "";
    try {
      const summary = await apiFetch(`/pharmacy/summary?${currentRangeParams().toString()}`);
      balanceCards.appendChild(statCard("Olingan dori (jami)", summary.total_medicine_cost));
      balanceCards.appendChild(statCard("To'langan (jami)", summary.total_paid));
      balanceCards.appendChild(statCard("Balans", summary.balance, true));
    } catch (err) {
      showError(errorContainer, err.detail || err.message || "Balansni yuklashda xatolik");
    }
  }

  entryForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    clearMessages();

    const payload = {
      date: document.getElementById("date").value || null,
      medicine_cost: moneyInputValue(document.getElementById("medicine_cost")) || null,
      amount_paid: moneyInputValue(document.getElementById("amount_paid")) || null,
      comment: document.getElementById("comment").value.trim() || null,
    };

    try {
      await apiFetch("/pharmacy/entries", { method: "POST", body: payload });
      entryForm.reset();
      await Promise.all([loadEntries(), loadBalance()]);
      showSuccess("Yozuv qo'shildi");
    } catch (err) {
      showError(errorContainer, err.detail || err.message || "Saqlashda xatolik yuz berdi");
    }
  });

  async function voidEntry(id) {
    if (!confirm("Ushbu yozuvni bekor qilasizmi?")) return;
    clearMessages();
    try {
      await apiFetch(`/pharmacy/entries/${id}/void`, { method: "POST" });
      await Promise.all([loadEntries(), loadBalance()]);
      showSuccess("Yozuv bekor qilindi");
    } catch (err) {
      showError(errorContainer, err.detail || err.message || "Bekor qilishda xatolik yuz berdi");
    }
  }

  async function loadEntries() {
    clearMessages();
    tbody.innerHTML = "";
    pagination.innerHTML = "";

    const params = currentRangeParams();
    params.set("page", page);
    params.set("page_size", pageSize);

    try {
      const data = await apiFetch(`/pharmacy/entries?${params.toString()}`);

      data.items.forEach((entry) => {
        const tr = document.createElement("tr");
        tr.innerHTML = `
          <td>${formatDate(entry.date)}</td>
          <td>${entry.medicine_cost != null ? formatMoney(entry.medicine_cost) : "—"}</td>
          <td>${entry.amount_paid != null ? formatMoney(entry.amount_paid) : "—"}</td>
          <td>${entry.comment ? escapeHtml(entry.comment) : "—"}</td>
          <td class="actions-cell"><button class="danger void-btn" data-id="${entry.id}">Bekor qilish</button></td>
        `;
        tbody.appendChild(tr);
      });

      tbody.querySelectorAll(".void-btn").forEach((btn) => {
        btn.addEventListener("click", () => voidEntry(btn.dataset.id));
      });

      pagination.innerHTML = `
        <button class="secondary" id="prev-page" ${page <= 1 ? "disabled" : ""}>Oldingi</button>
        <span>${paginationLabel(data)}</span>
        <button class="secondary" id="next-page" ${page >= data.pages ? "disabled" : ""}>Keyingi</button>
      `;
      const prevBtn = document.getElementById("prev-page");
      const nextBtn = document.getElementById("next-page");
      if (prevBtn) prevBtn.addEventListener("click", () => { page -= 1; loadEntries(); });
      if (nextBtn) nextBtn.addEventListener("click", () => { page += 1; loadEntries(); });
    } catch (err) {
      showError(errorContainer, err.detail || err.message || "Ro'yxatni yuklashda xatolik");
    }
  }

  document.getElementById("filter-form").addEventListener("submit", (event) => {
    event.preventDefault();
    page = 1;
    loadEntries();
    loadBalance();
  });

  await Promise.all([loadEntries(), loadBalance()]);
})();
