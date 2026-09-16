(async function () {
  const user = await initPage({ allowedRoles: ["superadmin", "manager"] });
  if (!user) return;

  const errorContainer = document.getElementById("error-container");
  const successContainer = document.getElementById("success-container");

  const staffSelects = [
    "balance_staff",
    "pay_staff",
    "history_staff",
    "lifetime_staff",
  ].map((id) => document.getElementById(id));

  const roleLabels = { doctor: "Shifokor", nurse: "Hamshira", other: "Boshqa" };
  const typeLabels = { full: "To'liq oylik", avans: "Avans" };

  let staffNameById = {};
  let historyPage = 1;
  const historyPageSize = 20;

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

  async function loadStaffOptions() {
    const options = await apiFetch("/staff/options");
    staffNameById = Object.fromEntries(options.map((s) => [s.id, s.name]));

    staffSelects.forEach((select) => {
      const keepFirst = select.id === "balance_staff" || select.id === "history_staff";
      select.innerHTML = keepFirst ? '<option value="">— barchasi —</option>' : "";
      options.forEach((opt) => {
        const el = document.createElement("option");
        el.value = opt.id;
        el.textContent = `${opt.name} (${roleLabels[opt.role] || opt.role})`;
        select.appendChild(el);
      });
    });
  }

  // --- Balance ---
  async function loadBalance() {
    const tbody = document.getElementById("balance-tbody");
    tbody.innerHTML = "";
    clearMessages();

    const params = new URLSearchParams();
    const staffId = document.getElementById("balance_staff").value;
    const from = document.getElementById("balance_from").value;
    const to = document.getElementById("balance_to").value;
    if (staffId) params.set("staff_id", staffId);
    if (from) params.set("date_from", from);
    if (to) params.set("date_to", to);

    try {
      const items = await apiFetch(`/salary/balance?${params.toString()}`);
      items.forEach((row) => {
        const tr = document.createElement("tr");
        tr.innerHTML = `
          <td>${row.name}</td>
          <td>${roleLabels[row.role] || row.role}</td>
          <td>${formatMoney(row.earned)}</td>
          <td>${formatMoney(row.paid)}</td>
          <td>${formatMoney(row.remaining)}</td>
        `;
        tbody.appendChild(tr);
      });
    } catch (err) {
      showError(errorContainer, err.detail || err.message || "Balansni yuklashda xatolik");
    }
  }

  document.getElementById("current-month-btn").addEventListener("click", () => {
    document.getElementById("balance_from").value = "";
    document.getElementById("balance_to").value = "";
    loadBalance();
  });

  document.getElementById("balance-form").addEventListener("submit", (event) => {
    event.preventDefault();
    loadBalance();
  });

  // --- Payment entry ---
  document.getElementById("payment-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    clearMessages();

    const payload = {
      staff_id: Number(document.getElementById("pay_staff").value),
      payment_type: document.getElementById("pay_type").value,
      period_start: document.getElementById("period_start").value,
      period_end: document.getElementById("period_end").value,
      amount: document.getElementById("pay_amount").value,
    };

    try {
      await apiFetch("/salary/payments", { method: "POST", body: payload });
      document.getElementById("payment-form").reset();
      await Promise.all([loadBalance(), loadHistory()]);
      showSuccess("To'lov qo'shildi");
    } catch (err) {
      showError(errorContainer, err.detail || err.message || "To'lovni saqlashda xatolik yuz berdi");
    }
  });

  // --- History ---
  async function voidPayment(id) {
    if (!confirm("Ushbu to'lovni bekor qilasizmi?")) return;
    clearMessages();
    try {
      await apiFetch(`/salary/payments/${id}/void`, { method: "POST" });
      await Promise.all([loadBalance(), loadHistory()]);
      showSuccess("To'lov bekor qilindi");
    } catch (err) {
      showError(errorContainer, err.detail || err.message || "Bekor qilishda xatolik yuz berdi");
    }
  }

  async function loadHistory() {
    const tbody = document.getElementById("history-tbody");
    const pagination = document.getElementById("history-pagination");
    tbody.innerHTML = "";
    pagination.innerHTML = "";
    clearMessages();

    const params = new URLSearchParams({ page: historyPage, page_size: historyPageSize });
    const staffId = document.getElementById("history_staff").value;
    const from = document.getElementById("history_from").value;
    const to = document.getElementById("history_to").value;
    if (staffId) params.set("staff_id", staffId);
    if (from) params.set("date_from", from);
    if (to) params.set("date_to", to);

    try {
      const data = await apiFetch(`/salary/payments?${params.toString()}`);

      data.items.forEach((payment) => {
        const tr = document.createElement("tr");
        tr.innerHTML = `
          <td>${payment.paid_at.slice(0, 10)}</td>
          <td>${staffNameById[payment.staff_id] || "—"}</td>
          <td>${typeLabels[payment.payment_type] || payment.payment_type}</td>
          <td>${payment.period_start} — ${payment.period_end}</td>
          <td>${formatMoney(payment.amount)}</td>
          <td class="actions-cell"><button class="danger void-btn" data-id="${payment.id}">Bekor qilish</button></td>
        `;
        tbody.appendChild(tr);
      });

      tbody.querySelectorAll(".void-btn").forEach((btn) => {
        btn.addEventListener("click", () => voidPayment(btn.dataset.id));
      });

      pagination.innerHTML = `
        <button class="secondary" id="history-prev" ${historyPage <= 1 ? "disabled" : ""}>Oldingi</button>
        <span>${paginationLabel(data)}</span>
        <button class="secondary" id="history-next" ${historyPage >= data.pages ? "disabled" : ""}>Keyingi</button>
      `;
      const prevBtn = document.getElementById("history-prev");
      const nextBtn = document.getElementById("history-next");
      if (prevBtn) prevBtn.addEventListener("click", () => { historyPage -= 1; loadHistory(); });
      if (nextBtn) nextBtn.addEventListener("click", () => { historyPage += 1; loadHistory(); });
    } catch (err) {
      showError(errorContainer, err.detail || err.message || "Tarixni yuklashda xatolik");
    }
  }

  document.getElementById("history-filter-form").addEventListener("submit", (event) => {
    event.preventDefault();
    historyPage = 1;
    loadHistory();
  });

  // --- Lifetime summary ---
  function statCard(label, value) {
    const div = document.createElement("div");
    div.className = "stat-card";
    div.innerHTML = `<div class="label">${label}</div><div class="value">${formatMoney(value)}</div>`;
    return div;
  }

  document.getElementById("lifetime-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    clearMessages();
    const cards = document.getElementById("lifetime-cards");
    cards.innerHTML = "";

    const staffId = document.getElementById("lifetime_staff").value;
    if (!staffId) return;

    try {
      const summary = await apiFetch(`/salary/staff/${staffId}/summary`);
      cards.appendChild(statCard("Umumiy ishlab topgani", summary.lifetime_earned));
      cards.appendChild(statCard("Umumiy to'langan", summary.lifetime_paid));
      cards.appendChild(statCard("Qoldiq", summary.lifetime_remaining));
    } catch (err) {
      showError(errorContainer, err.detail || err.message || "Statistikani yuklashda xatolik");
    }
  });

  await loadStaffOptions();
  await Promise.all([loadBalance(), loadHistory()]);
})();
