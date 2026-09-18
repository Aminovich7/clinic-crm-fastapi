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

  attachMoneyInput(document.getElementById("amount"));

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

  // `unit` is omitted for plain counts — "Yozuvlar soni" is a number of
  // records, not an amount of money.
  function statCard(label, value, variant, unit = "so'm") {
    const div = document.createElement("div");
    div.className = `stat-card${variant ? ` stat-card--${variant}` : ""}`;
    div.innerHTML =
      `<div class="label">${label}</div>` +
      `<div class="value">${formatMoney(value)}${unit ? `<span class="unit">${unit}</span>` : ""}</div>`;
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
      summaryCards.appendChild(statCard("Jami summa", summary.total_amount, "warning"));
      summaryCards.appendChild(statCard("Yozuvlar soni", summary.count, "primary", ""));
    } catch (err) {
      showError(errorContainer, err.detail || err.message || "Statistikani yuklashda xatolik");
    }
  }

  expenseForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    clearMessages();

    const payload = {
      title: document.getElementById("title").value,
      amount: moneyInputValue(document.getElementById("amount")),
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
      const data = await withLoading(tbody.closest("table"), () => apiFetch(`/expenses?${params.toString()}`));

      if (data.items.length === 0) {
        renderEmpty(tbody, columnCount(tbody.closest("table")), "Ma'lumot topilmadi");
      }
      data.items.forEach((expense) => {
        const tr = document.createElement("tr");
        tr.innerHTML = `
          <td>${formatDate(expense.date)}</td>
          <td>${escapeHtml(expense.title)}</td>
          <td class="num">${formatMoney(expense.amount)}</td>
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

  attachMonthShortcuts({
    fromInput: dateFromInput,
    toInput: dateToInput,
    currentBtn: document.getElementById("current-month-btn"),
    previousBtn: document.getElementById("previous-month-btn"),
    labelEl: document.getElementById("period-label"),
    onApply: () => {
      searchTerm = searchInput.value.trim();
      page = 1;
      loadExpenses();
      loadSummary();
    },
  });

  await Promise.all([loadExpenses(), loadSummary()]);
})();
