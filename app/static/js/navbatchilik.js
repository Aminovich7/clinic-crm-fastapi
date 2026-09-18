(async function () {
  const user = await initPage({ allowedRoles: ["superadmin", "manager"] });
  if (!user) return;

  const errorContainer = document.getElementById("error-container");
  const successContainer = document.getElementById("success-container");
  const tbody = document.getElementById("duty-tbody");
  const pagination = document.getElementById("pagination");
  const filterStaffSelect = document.getElementById("filter_staff");
  const staffSelect = document.getElementById("staff");
  const dutyForm = document.getElementById("duty-form");

  attachMoneyInput(document.getElementById("amount"));

  let page = 1;
  const pageSize = 20;
  let staffFilter = "";
  let dateFrom = "";
  let dateTo = "";
  let staffNameById = {};

  const roleLabels = { doctor: "Shifokor", nurse: "Hamshira", other: "Boshqa" };

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

    [filterStaffSelect, staffSelect].forEach((select) => {
      const keepFirst = select === filterStaffSelect;
      select.innerHTML = keepFirst ? '<option value="">— barchasi —</option>' : "";
      options.forEach((opt) => {
        const el = document.createElement("option");
        el.value = opt.id;
        el.textContent = `${opt.name} (${roleLabels[opt.role] || opt.role})`;
        select.appendChild(el);
      });
    });
  }

  dutyForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    clearMessages();

    const payload = {
      staff_id: Number(document.getElementById("staff").value),
      date: document.getElementById("date").value || null,
      amount: moneyInputValue(document.getElementById("amount")),
    };

    try {
      await apiFetch("/duty-entries", { method: "POST", body: payload });
      dutyForm.reset();
      await loadDutyEntries();
      showSuccess("Navbatchilik qo'shildi");
    } catch (err) {
      showError(errorContainer, err.detail || err.message || "Saqlashda xatolik yuz berdi");
    }
  });

  async function voidEntry(id) {
    if (!confirm("Ushbu yozuvni bekor qilasizmi?")) return;
    clearMessages();
    try {
      await apiFetch(`/duty-entries/${id}/void`, { method: "POST" });
      await loadDutyEntries();
      showSuccess("Yozuv bekor qilindi");
    } catch (err) {
      showError(errorContainer, err.detail || err.message || "Bekor qilishda xatolik yuz berdi");
    }
  }


  async function loadDutyEntries() {
    clearMessages();
    tbody.innerHTML = "";
    pagination.innerHTML = "";

    const params = new URLSearchParams({ page, page_size: pageSize });
    if (staffFilter) params.set("staff_id", staffFilter);
    if (dateFrom) params.set("date_from", dateFrom);
    if (dateTo) params.set("date_to", dateTo);

    try {
      const data = await withLoading(tbody.closest("table"), () => apiFetch(`/duty-entries?${params.toString()}`));

      if (data.items.length === 0) {
        renderEmpty(tbody, columnCount(tbody.closest("table")), "Ma'lumot topilmadi");
      }
      data.items.forEach((entry) => {
        const tr = document.createElement("tr");
        tr.innerHTML = `
          <td>${formatDate(entry.date)}</td>
          <td>${escapeHtml(staffNameById[entry.staff_id] || "—")}</td>
          <td class="num">${formatMoney(entry.amount)}</td>
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
      if (prevBtn) prevBtn.addEventListener("click", () => { page -= 1; loadDutyEntries(); });
      if (nextBtn) nextBtn.addEventListener("click", () => { page += 1; loadDutyEntries(); });
    } catch (err) {
      showError(errorContainer, err.detail || err.message || "Ro'yxatni yuklashda xatolik");
    }
  }

  document.getElementById("filter-form").addEventListener("submit", (event) => {
    event.preventDefault();
    staffFilter = filterStaffSelect.value;
    dateFrom = document.getElementById("date_from").value;
    dateTo = document.getElementById("date_to").value;
    page = 1;
    loadDutyEntries();
  });

  attachMonthShortcuts({
    fromInput: document.getElementById("date_from"),
    toInput: document.getElementById("date_to"),
    currentBtn: document.getElementById("current-month-btn"),
    previousBtn: document.getElementById("previous-month-btn"),
    labelEl: document.getElementById("period-label"),
    // This page keeps the active filter in module-level state that only the
    // submit handler refreshes, so the shortcut has to update it too.
    onApply: () => {
      staffFilter = filterStaffSelect.value;
      dateFrom = document.getElementById("date_from").value;
      dateTo = document.getElementById("date_to").value;
      page = 1;
      loadDutyEntries();
    },
  });

  await loadStaffOptions();
  await loadDutyEntries();
})();
