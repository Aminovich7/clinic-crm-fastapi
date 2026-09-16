(async function () {
  const user = await initPage();
  if (!user) return;

  const canManage = user.role === "superadmin" || user.role === "manager";
  // Assistants create receipts but must never see the clinic's internal
  // economics (doctor share / clinic profit / expense breakdown) — only
  // superadmin/manager get the live preview under each form.
  const showPreview = user.role !== "assistant";

  const errorContainer = document.getElementById("error-container");
  const successContainer = document.getElementById("success-container");
  const recentThead = document.getElementById("recent-thead");
  const recentTbody = document.getElementById("recent-tbody");
  const pagination = document.getElementById("pagination");

  if (!showPreview) {
    ["c_preview", "s_preview", "r_preview"].forEach((id) => {
      document.getElementById(id).classList.add("hidden");
    });
  }

  let activeTab = "consultation";
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

  // --- Tabs ---
  document.querySelectorAll(".tab-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      activeTab = btn.dataset.tab;
      document.querySelectorAll(".tab-btn").forEach((b) => b.classList.toggle("active", b === btn));
      document.querySelectorAll(".tab-panel").forEach((panel) => {
        panel.classList.toggle("hidden", panel.id !== `panel-${activeTab}`);
      });
      page = 1;
      loadRecent();
    });
  });

  // --- Doctor dropdowns ---
  // Also used to render the doctor's name in the recent-entries table —
  // finance records only carry doctor_id, not the name, so this map is
  // the only source for that column.
  let doctorNameById = {};

  async function loadDoctorOptions() {
    try {
      const options = await apiFetch("/staff/options?role=doctor");
      doctorNameById = Object.fromEntries(options.map((doc) => [doc.id, doc.name]));
      ["c_doctor", "s_doctor", "r_doctor"].forEach((id) => {
        const select = document.getElementById(id);
        select.innerHTML = '<option value="">— tanlanmagan —</option>';
        options.forEach((doc) => {
          const opt = document.createElement("option");
          opt.value = doc.id;
          opt.textContent = doc.name;
          select.appendChild(opt);
        });
      });
      const filterDoctorSelect = document.getElementById("filter_doctor");
      filterDoctorSelect.innerHTML = '<option value="">— barcha shifokorlar —</option>';
      options.forEach((doc) => {
        const opt = document.createElement("option");
        opt.value = doc.id;
        opt.textContent = doc.name;
        filterDoctorSelect.appendChild(opt);
      });
    } catch (err) {
      showError(errorContainer, err.detail || err.message || "Shifokorlar ro'yxatini yuklashda xatolik");
    }
  }

  // --- "Added by" data: used both for the recent-entries table's
  // "Qo'shdi" column (every role) and the "Kim qo'shgan" filter
  // (superadmin/manager only — an assistant's list is already forced to
  // their own records, so the filter would be a no-op for them).
  let creatorNameById = { [user.id]: user.full_name };

  async function loadCreatorOptions() {
    const filterCreatorField = document.getElementById("filter-creator-field");
    if (!canManage) {
      filterCreatorField.classList.add("hidden");
      return;
    }
    filterCreatorField.classList.remove("hidden");

    const people = [{ id: user.id, name: `${user.full_name} (siz)` }];
    try {
      if (user.role === "superadmin") {
        const managers = await apiFetch("/users/managers?page_size=100");
        managers.items.forEach((m) => {
          if (m.id !== user.id) people.push({ id: m.id, name: m.full_name });
        });
      }
      const assistants = await apiFetch("/users/assistants?page_size=100");
      assistants.items.forEach((a) => people.push({ id: a.id, name: a.full_name }));
    } catch (err) {
      showError(errorContainer, err.detail || err.message || "Foydalanuvchilar ro'yxatini yuklashda xatolik");
    }

    creatorNameById = Object.fromEntries(people.map((p) => [p.id, p.name]));
    const select = document.getElementById("filter_creator");
    select.innerHTML = '<option value="">— hammasi —</option>';
    people.forEach((p) => {
      const opt = document.createElement("option");
      opt.value = p.id;
      opt.textContent = p.name;
      select.appendChild(opt);
    });
  }

  // --- Client-side preview math (mirrors app/finance/calculations.py) ---
  // Only ever called when showPreview is true.
  function round2(n) {
    return Math.round(n);
  }

  function updateConsultationPreview() {
    if (!showPreview) return;
    const amount = parseFloat(moneyInputValue(document.getElementById("c_amount"))) || 0;
    const percent = parseFloat(document.getElementById("c_doctor_percent").value) || 0;
    const minusInput = moneyInputValue(document.getElementById("c_minus_beshming"));
    const usesDefault = minusInput === "";
    const minus = usesDefault ? 0 : parseFloat(minusInput);
    const doctorShare = round2((amount - minus) * percent / 100);
    const clinicProfit = round2(amount - doctorShare - minus);
    const note = usesDefault
      ? " (klinikaning standart xarajati qo'llaniladi — bo'sh qoldirilsa shu qiymat ishlatiladi, haqiqiy son farq qilishi mumkin)"
      : "";
    document.getElementById("c_preview").textContent =
      `Taxminiy hisob — shifokor ulushi: ${formatMoney(doctorShare)}, klinika foydasi: ${formatMoney(clinicProfit)}, xarajat: ${formatMoney(minus)}${note}`;
  }

  function updateSurgeryPreview() {
    if (!showPreview) return;
    const amount = parseFloat(moneyInputValue(document.getElementById("s_amount"))) || 0;
    const percent = parseFloat(document.getElementById("s_doctor_percent").value) || 0;
    const expense = parseFloat(moneyInputValue(document.getElementById("s_surgery_expense"))) || 0;
    const doctorShare = round2((amount - expense) * percent / 100);
    const clinicProfit = round2(amount - doctorShare - expense);
    document.getElementById("s_preview").textContent =
      `Taxminiy hisob — shifokor ulushi: ${formatMoney(doctorShare)}, klinika foydasi: ${formatMoney(clinicProfit)}, xarajat: ${formatMoney(expense)}`;
  }

  function updateRoomPreview() {
    if (!showPreview) return;
    const amount = parseFloat(moneyInputValue(document.getElementById("r_amount"))) || 0;
    const percent = parseFloat(document.getElementById("r_doctor_percent").value) || 0;
    const doctorShare = round2(amount * percent / 100);
    const clinicProfit = round2(amount - doctorShare);
    document.getElementById("r_preview").textContent =
      `Taxminiy hisob — shifokor ulushi: ${formatMoney(doctorShare)}, klinika foydasi: ${formatMoney(clinicProfit)}`;
  }

  // Comma-format every money-amount field as the user types, regardless
  // of role — this is independent of the preview (assistants don't see
  // the preview but still type amounts).
  ["c_amount", "c_minus_beshming", "s_amount", "s_surgery_expense", "r_amount"].forEach((id) =>
    attachMoneyInput(document.getElementById(id))
  );

  if (showPreview) {
    ["c_amount", "c_doctor_percent", "c_minus_beshming"].forEach((id) =>
      document.getElementById(id).addEventListener("input", updateConsultationPreview)
    );
    ["s_amount", "s_doctor_percent", "s_surgery_expense"].forEach((id) =>
      document.getElementById(id).addEventListener("input", updateSurgeryPreview)
    );
    ["r_amount", "r_doctor_percent"].forEach((id) =>
      document.getElementById(id).addEventListener("input", updateRoomPreview)
    );
  }

  // --- Create/edit handlers ---
  function toIsoOrUndefined(value) {
    return value ? new Date(value).toISOString() : undefined;
  }

  // Converts a server ISO timestamp to the local wall-clock string a
  // datetime-local input expects, using the same browser-local
  // interpretation toIsoOrUndefined() relies on for the reverse direction.
  function toLocalInputValue(isoString) {
    const d = new Date(isoString);
    const pad = (n) => String(n).padStart(2, "0");
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
  }

  // Per-tab edit state: which record (if any) each form is currently
  // editing, and the last page of records loaded for that tab (so an Edit
  // click can look up the full record without a redundant GET /{id}).
  const editingId = { consultation: null, surgery: null, room: null };
  let lastLoadedItems = [];

  function enterEditMode(kind, record) {
    editingId[kind] = record.id;

    if (kind === "consultation") {
      document.getElementById("c_id").value = record.id;
      document.getElementById("c_type").value = record.type;
      document.getElementById("c_receipt_number").value = record.receipt_number;
      document.getElementById("c_date").value = toLocalInputValue(record.date);
      document.getElementById("c_doctor").value = record.doctor_id ?? "";
      document.getElementById("c_amount").value = formatMoneyInputValue(record.amount);
      document.getElementById("c_doctor_percent").value = record.doctor_percent;
      document.getElementById("c_minus_beshming").value = formatMoneyInputValue(record.minus_beshming ?? 0);
      document.getElementById("c_form_title").textContent = `Ko'rikni tahrirlash — chek #${record.receipt_number}`;
      document.getElementById("c_submit_btn").textContent = "Saqlash";
      document.getElementById("c_cancel_btn").classList.remove("hidden");
      updateConsultationPreview();
    } else if (kind === "surgery") {
      document.getElementById("s_id").value = record.id;
      document.getElementById("s_receipt_number").value = record.receipt_number;
      document.getElementById("s_date").value = toLocalInputValue(record.date);
      document.getElementById("s_doctor").value = record.doctor_id ?? "";
      document.getElementById("s_amount").value = formatMoneyInputValue(record.amount);
      document.getElementById("s_surgery_expense").value = formatMoneyInputValue(record.surgery_expense);
      document.getElementById("s_doctor_percent").value = record.doctor_percent;
      document.getElementById("s_form_title").textContent = `Operatsiyani tahrirlash — chek #${record.receipt_number}`;
      document.getElementById("s_submit_btn").textContent = "Saqlash";
      document.getElementById("s_cancel_btn").classList.remove("hidden");
      updateSurgeryPreview();
    } else {
      document.getElementById("r_id").value = record.id;
      document.getElementById("r_receipt_number").value = record.receipt_number ?? "";
      document.getElementById("r_date").value = toLocalInputValue(record.date);
      document.getElementById("r_doctor").value = record.doctor_id ?? "";
      document.getElementById("r_amount").value = formatMoneyInputValue(record.amount);
      document.getElementById("r_doctor_percent").value = record.doctor_percent;
      document.getElementById("r_form_title").textContent = `Xona yozuvini tahrirlash — #${record.receipt_number ?? record.id}`;
      document.getElementById("r_submit_btn").textContent = "Saqlash";
      document.getElementById("r_cancel_btn").classList.remove("hidden");
      updateRoomPreview();
    }

    activeTab = kind;
    document.querySelectorAll(".tab-btn").forEach((b) => b.classList.toggle("active", b.dataset.tab === kind));
    document.querySelectorAll(".tab-panel").forEach((panel) => {
      panel.classList.toggle("hidden", panel.id !== `panel-${kind}`);
    });
  }

  function exitEditMode(kind) {
    editingId[kind] = null;
    const form = document.getElementById(`${kind}-form`);
    form.reset();
    const prefix = kind === "consultation" ? "c" : kind === "surgery" ? "s" : "r";
    document.getElementById(`${prefix}_id`).value = "";
    document.getElementById(`${prefix}_form_title`).textContent =
      kind === "consultation" ? "Yangi ko'rik" : kind === "surgery" ? "Yangi operatsiya" : "Yangi xona";
    document.getElementById(`${prefix}_submit_btn`).textContent = "Qo'shish";
    document.getElementById(`${prefix}_cancel_btn`).classList.add("hidden");
    document.getElementById(`${prefix}_preview`).textContent = "";
  }

  document.getElementById("c_cancel_btn").addEventListener("click", () => exitEditMode("consultation"));
  document.getElementById("s_cancel_btn").addEventListener("click", () => exitEditMode("surgery"));
  document.getElementById("r_cancel_btn").addEventListener("click", () => exitEditMode("room"));

  document.getElementById("consultation-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    clearMessages();
    const id = editingId.consultation;
    const minusInput = moneyInputValue(document.getElementById("c_minus_beshming"));
    const payload = {
      type: document.getElementById("c_type").value,
      receipt_number: Number(document.getElementById("c_receipt_number").value),
      date: toIsoOrUndefined(document.getElementById("c_date").value),
      doctor_id: document.getElementById("c_doctor").value || null,
      amount: moneyInputValue(document.getElementById("c_amount")),
      doctor_percent: document.getElementById("c_doctor_percent").value,
      // On create, blank means "apply the clinic's dynamic default" (send
      // null, per §4). On edit, blank means "clear it to zero for this
      // record" (§4's PATCH note) — sending null here would do that too,
      // but 0 is unambiguous and matches what the field will redisplay.
      minus_beshming: minusInput !== "" ? minusInput : id ? "0" : null,
    };
    try {
      if (id) {
        await apiFetch(`/consultations/${id}`, { method: "PATCH", body: payload });
      } else {
        await apiFetch("/consultations", { method: "POST", body: payload });
      }
      exitEditMode("consultation");
      if (activeTab === "consultation") await loadRecent();
      showSuccess(id ? "Ko'rik yangilandi" : "Ko'rik qo'shildi");
    } catch (err) {
      showError(errorContainer, err.detail || err.message || "Ko'rikni saqlashda xatolik yuz berdi");
    }
  });

  document.getElementById("surgery-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    clearMessages();
    const id = editingId.surgery;
    const payload = {
      receipt_number: Number(document.getElementById("s_receipt_number").value),
      date: toIsoOrUndefined(document.getElementById("s_date").value),
      doctor_id: document.getElementById("s_doctor").value || null,
      amount: moneyInputValue(document.getElementById("s_amount")),
      surgery_expense: moneyInputValue(document.getElementById("s_surgery_expense")),
      doctor_percent: document.getElementById("s_doctor_percent").value,
    };
    try {
      if (id) {
        await apiFetch(`/surgeries/${id}`, { method: "PATCH", body: payload });
      } else {
        await apiFetch("/surgeries", { method: "POST", body: payload });
      }
      exitEditMode("surgery");
      if (activeTab === "surgery") await loadRecent();
      showSuccess(id ? "Operatsiya yangilandi" : "Operatsiya qo'shildi");
    } catch (err) {
      showError(errorContainer, err.detail || err.message || "Operatsiyani saqlashda xatolik yuz berdi");
    }
  });

  document.getElementById("room-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    clearMessages();
    const id = editingId.room;
    const receiptInput = document.getElementById("r_receipt_number").value;
    const payload = {
      receipt_number: receiptInput ? Number(receiptInput) : null,
      date: toIsoOrUndefined(document.getElementById("r_date").value),
      doctor_id: document.getElementById("r_doctor").value || null,
      amount: moneyInputValue(document.getElementById("r_amount")),
      doctor_percent: document.getElementById("r_doctor_percent").value,
    };
    try {
      if (id) {
        await apiFetch(`/rooms/${id}`, { method: "PATCH", body: payload });
      } else {
        await apiFetch("/rooms", { method: "POST", body: payload });
      }
      exitEditMode("room");
      if (activeTab === "room") await loadRecent();
      showSuccess(id ? "Xona yozuvi yangilandi" : "Xona yozuvi qo'shildi");
    } catch (err) {
      showError(errorContainer, err.detail || err.message || "Xona yozuvini saqlashda xatolik yuz berdi");
    }
  });

  // --- Recent entries list ---
  const ENDPOINTS = {
    consultation: "/consultations",
    surgery: "/surgeries",
    room: "/rooms",
  };

  // Base columns, before the role-conditional "Klinika foydasi" column
  // (manager/superadmin only — mirrors the create-form preview's
  // restriction, §Session 8) gets spliced in just before "Holati".
  const BASE_HEADERS = {
    consultation: ["Chek raqami", "Sana", "Turi", "Shifokor", "Qo'shdi", "Summa", "Shifokor foizi", "Xarajat", "Holati", "Amallar"],
    surgery: ["Chek raqami", "Sana", "Shifokor", "Qo'shdi", "Summa", "Shifokor foizi", "Xarajat", "Holati", "Amallar"],
    room: ["Chek raqami", "Sana", "Shifokor", "Qo'shdi", "Summa", "Shifokor foizi", "Holati", "Amallar"],
  };

  function headersFor(kind) {
    const headers = [...BASE_HEADERS[kind]];
    if (canManage) {
      headers.splice(headers.indexOf("Holati"), 0, "Klinika foydasi");
    }
    return headers;
  }

  // Mirrors app/finance/calculations.py exactly (never persisted server-
  // side, so it has to be recomputed here the same way the create-form
  // preview does it).
  function computeClinicProfit(kind, record) {
    const amount = Number(record.amount);
    const percent = Number(record.doctor_percent);
    if (kind === "room") {
      const doctorShare = Math.round((amount * percent) / 100);
      return amount - doctorShare;
    }
    const expense = Number(kind === "consultation" ? record.minus_beshming ?? 0 : record.surgery_expense);
    const doctorShare = Math.round(((amount - expense) * percent) / 100);
    return amount - doctorShare - expense;
  }

  async function voidRecord(kind, id) {
    if (!confirm("Ushbu yozuvni bekor qilasizmi? Bu amalni qaytarib bo'lmaydi.")) return;
    clearMessages();
    try {
      await apiFetch(`${ENDPOINTS[kind]}/${id}/void`, { method: "POST" });
      await loadRecent();
      showSuccess("Yozuv bekor qilindi");
    } catch (err) {
      showError(errorContainer, err.detail || err.message || "Yozuvni bekor qilishda xatolik yuz berdi");
    }
  }

  function renderRow(kind, record) {
    const tr = document.createElement("tr");
    if (record.is_voided) tr.classList.add("voided");

    const dateStr = formatDateTime(record.date);
    const editBtn =
      canManage && !record.is_voided
        ? `<button class="secondary edit-record-btn" data-kind="${kind}" data-id="${record.id}">Tahrirlash</button>`
        : "";
    const voidBtn =
      canManage && !record.is_voided
        ? `<button class="danger void-btn" data-kind="${kind}" data-id="${record.id}">Bekor qilish</button>`
        : "";
    const statusLabel = record.is_voided ? "Bekor qilingan" : "Faol";
    const typeLabel = record.type === "korik" ? "Ko'rik" : "Qayta ko'rik";
    const doctorLabel = record.doctor_id ? (doctorNameById[record.doctor_id] || "—") : "—";
    const creatorLabel = creatorNameById[record.created_by_id] || "—";
    const profitCell = canManage ? `<td>${formatMoney(computeClinicProfit(kind, record))}</td>` : "";

    if (kind === "consultation") {
      tr.innerHTML = `
        <td>${record.receipt_number}</td>
        <td>${dateStr}</td>
        <td>${typeLabel}</td>
        <td>${doctorLabel}</td>
        <td>${creatorLabel}</td>
        <td>${formatMoney(record.amount)}</td>
        <td>${formatMoney(record.doctor_percent)}%</td>
        <td>${formatMoney(record.minus_beshming ?? 0)}</td>
        ${profitCell}
        <td>${statusLabel}</td>
        <td class="actions-cell">${editBtn}${voidBtn}</td>
      `;
    } else if (kind === "surgery") {
      tr.innerHTML = `
        <td>${record.receipt_number}</td>
        <td>${dateStr}</td>
        <td>${doctorLabel}</td>
        <td>${creatorLabel}</td>
        <td>${formatMoney(record.amount)}</td>
        <td>${formatMoney(record.doctor_percent)}%</td>
        <td>${formatMoney(record.surgery_expense)}</td>
        ${profitCell}
        <td>${statusLabel}</td>
        <td class="actions-cell">${editBtn}${voidBtn}</td>
      `;
    } else {
      tr.innerHTML = `
        <td>${record.receipt_number ?? "—"}</td>
        <td>${dateStr}</td>
        <td>${doctorLabel}</td>
        <td>${creatorLabel}</td>
        <td>${formatMoney(record.amount)}</td>
        <td>${formatMoney(record.doctor_percent)}%</td>
        ${profitCell}
        <td>${statusLabel}</td>
        <td class="actions-cell">${editBtn}${voidBtn}</td>
      `;
    }
    return tr;
  }

  // --- Filters ---
  const filterDateFromInput = document.getElementById("filter_date_from");
  const filterDateToInput = document.getElementById("filter_date_to");
  const filterDoctorSelect = document.getElementById("filter_doctor");
  const filterCreatorSelect = document.getElementById("filter_creator");

  document.getElementById("filter-form").addEventListener("submit", (event) => {
    event.preventDefault();
    page = 1;
    loadRecent();
  });

  document.getElementById("filter-clear-btn").addEventListener("click", () => {
    filterDateFromInput.value = "";
    filterDateToInput.value = "";
    filterDoctorSelect.value = "";
    if (filterCreatorSelect) filterCreatorSelect.value = "";
    page = 1;
    loadRecent();
  });

  async function loadRecent() {
    clearMessages();
    recentTbody.innerHTML = "";
    pagination.innerHTML = "";
    recentThead.innerHTML = `<tr>${headersFor(activeTab).map((h) => `<th>${h}</th>`).join("")}</tr>`;

    const params = new URLSearchParams({ page, page_size: pageSize });
    if (filterDateFromInput.value) params.set("date_from", filterDateFromInput.value);
    if (filterDateToInput.value) params.set("date_to", filterDateToInput.value);
    if (filterDoctorSelect.value) params.set("doctor_id", filterDoctorSelect.value);
    if (canManage && filterCreatorSelect.value) params.set("created_by_id", filterCreatorSelect.value);
    try {
      const data = await apiFetch(`${ENDPOINTS[activeTab]}?${params.toString()}`);
      lastLoadedItems = data.items;
      data.items.forEach((record) => recentTbody.appendChild(renderRow(activeTab, record)));

      recentTbody.querySelectorAll(".void-btn").forEach((btn) => {
        btn.addEventListener("click", () => voidRecord(btn.dataset.kind, btn.dataset.id));
      });
      recentTbody.querySelectorAll(".edit-record-btn").forEach((btn) => {
        btn.addEventListener("click", () => {
          const record = lastLoadedItems.find((r) => String(r.id) === btn.dataset.id);
          if (record) enterEditMode(btn.dataset.kind, record);
        });
      });

      pagination.innerHTML = `
        <button class="secondary" id="prev-page" ${page <= 1 ? "disabled" : ""}>Oldingi</button>
        <span>${paginationLabel(data)}</span>
        <button class="secondary" id="next-page" ${page >= data.pages ? "disabled" : ""}>Keyingi</button>
      `;
      const prevBtn = document.getElementById("prev-page");
      const nextBtn = document.getElementById("next-page");
      if (prevBtn) prevBtn.addEventListener("click", () => { page -= 1; loadRecent(); });
      if (nextBtn) nextBtn.addEventListener("click", () => { page += 1; loadRecent(); });
    } catch (err) {
      showError(errorContainer, err.detail || err.message || "Yozuvlarni yuklashda xatolik");
    }
  }

  await Promise.all([loadDoctorOptions(), loadCreatorOptions()]);
  loadRecent();
})();
