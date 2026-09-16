(async function () {
  const user = await initPage({ allowedRoles: ["superadmin", "manager"] });
  if (!user) return;

  const errorContainer = document.getElementById("error-container");
  const successContainer = document.getElementById("success-container");
  const tbody = document.getElementById("expenses-tbody");
  const pagination = document.getElementById("pagination");
  const summaryCards = document.getElementById("summary-cards");
  const expenseForm = document.getElementById("expense-form");
  const dateFromInput = document.getElementById("date_from");
  const dateToInput = document.getElementById("date_to");
  const searchInput = document.getElementById("search");

  let page = 1;
  const pageSize = 20;
  let searchTerm = "";

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

  function statCard(label, value) {
    const div = document.createElement("div");
    div.className = "stat-card";
    div.innerHTML = `<div class="label">${label}</div><div class="value">${formatMoney(value)}</div>`;
    return div;
  }

  function currentParams() {
    const params = new URLSearchParams();
    if (dateFromInput.value) params.set("date_from", dateFromInput.value);
    if (dateToInput.value) params.set("date_to", dateToInput.value);
    if (searchTerm) params.set("search", searchTerm);
    return params;
  }

  async function loadSummary() {
    summaryCards.innerHTML = "";
    try {
      const summary = await apiFetch(`/expenses/summary?${currentParams().toString()}`);
      summaryCards.appendChild(statCard("Jami summa", summary.total_amount));
      summaryCards.appendChild(statCard("Yozuvlar soni", summary.count));
    } catch (err) {
      showError(errorContainer, err.detail || err.message || "Statistikani yuklashda xatolik");
    }
  }

  expenseForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    clearMessages();

    const payload = {
      title: document.getElementById("title").value,
      amount: document.getElementById("amount").value,
      date: document.getElementById("date").value || null,
    };

    try {
      await apiFetch("/expenses", { method: "POST", body: payload });
      expenseForm.reset();
      await Promise.all([loadExpenses(), loadSummary()]);
      showSuccess("Xarajat qo'shildi");
    } catch (err) {
      showError(errorContainer, err.detail || err.message || "Saqlashda xatolik yuz berdi");
    }
  });

  async function voidExpense(id) {
    if (!confirm("Ushbu xarajatni bekor qilasizmi?")) return;
    clearMessages();
    try {
      await apiFetch(`/expenses/${id}/void`, { method: "POST" });
      await Promise.all([loadExpenses(), loadSummary()]);
      showSuccess("Xarajat bekor qilindi");
    } catch (err) {
      showError(errorContainer, err.detail || err.message || "Bekor qilishda xatolik yuz berdi");
    }
  }

  async function loadExpenses() {
    clearMessages();
    tbody.innerHTML = "";
    pagination.innerHTML = "";

    const params = currentParams();
    params.set("page", page);
    params.set("page_size", pageSize);

    try {
      const data = await apiFetch(`/expenses?${params.toString()}`);

      data.items.forEach((expense) => {
        const tr = document.createElement("tr");
        tr.innerHTML = `
          <td>${expense.date.slice(0, 10)}</td>
          <td>${expense.title}</td>
          <td>${formatMoney(expense.amount)}</td>
          <td class="actions-cell"><button class="danger void-btn" data-id="${expense.id}">Bekor qilish</button></td>
        `;
        tbody.appendChild(tr);
      });

      tbody.querySelectorAll(".void-btn").forEach((btn) => {
        btn.addEventListener("click", () => voidExpense(btn.dataset.id));
      });

      pagination.innerHTML = `
        <button class="secondary" id="prev-page" ${page <= 1 ? "disabled" : ""}>Oldingi</button>
        <span>${paginationLabel(data)}</span>
        <button class="secondary" id="next-page" ${page >= data.pages ? "disabled" : ""}>Keyingi</button>
      `;
      const prevBtn = document.getElementById("prev-page");
      const nextBtn = document.getElementById("next-page");
      if (prevBtn) prevBtn.addEventListener("click", () => { page -= 1; loadExpenses(); });
      if (nextBtn) nextBtn.addEventListener("click", () => { page += 1; loadExpenses(); });
    } catch (err) {
      showError(errorContainer, err.detail || err.message || "Ro'yxatni yuklashda xatolik");
    }
  }

  document.getElementById("filter-form").addEventListener("submit", (event) => {
    event.preventDefault();
    searchTerm = searchInput.value.trim();
    page = 1;
    loadExpenses();
    loadSummary();
  });

  await Promise.all([loadExpenses(), loadSummary()]);
})();
