// Audit jurnali — the one place voided records are seen and acted on.
// The ordinary record pages list live records only, so Tiklash (restore) and
// O'chirish (permanent delete) exist here and nowhere else.
(async function () {
  const user = await initPage({ allowedRoles: ["superadmin"] });
  if (!user) return;

  const errorContainer = document.getElementById("error-container");
  const successContainer = document.getElementById("success-container");
  const tbody = document.getElementById("voided-tbody");
  const pagination = document.getElementById("voided-pagination");
  const typeSelect = document.getElementById("voided_resource_type");

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

  // Where restore/delete live for each voidable resource.
  const RESOURCE_ENDPOINTS = {
    consultation: "/consultations",
    surgery: "/surgeries",
    room: "/rooms",
    duty_entry: "/duty-entries",
    expense: "/expenses",
    pharmacy_entry: "/pharmacy/entries",
    salary_payment: "/salary/payments",
  };

  const RESOURCE_LABELS = {
    consultation: "Ko'rik",
    surgery: "Operatsiya",
    room: "Xona",
    duty_entry: "Navbatchilik",
    expense: "Xarajat",
    pharmacy_entry: "Dorixona",
    salary_payment: "Oylik to'lovi",
  };

  typeSelect.innerHTML = '<option value="">— barchasi —</option>';
  Object.keys(RESOURCE_ENDPOINTS).forEach((type) => {
    const opt = document.createElement("option");
    opt.value = type;
    opt.textContent = RESOURCE_LABELS[type];
    typeSelect.appendChild(opt);
  });

  async function restoreRecord(resourceType, id) {
    if (!confirm(RESTORE_CONFIRM)) return;
    clearMessages();
    try {
      await apiFetch(`${RESOURCE_ENDPOINTS[resourceType]}/${id}/restore`, { method: "POST" });
      await loadVoided();
      showSuccess("Yozuv tiklandi");
    } catch (err) {
      showError(errorContainer, err.detail || err.message || "Yozuvni tiklashda xatolik yuz berdi");
    }
  }

  async function deleteRecord(resourceType, id) {
    if (!confirm(DELETE_CONFIRM)) return;
    clearMessages();
    try {
      await apiFetch(`${RESOURCE_ENDPOINTS[resourceType]}/${id}`, { method: "DELETE" });
      await loadVoided();
      showSuccess("Yozuv butunlay o'chirildi");
    } catch (err) {
      showError(errorContainer, err.detail || err.message || "Yozuvni o'chirishda xatolik yuz berdi");
    }
  }

  async function loadVoided() {
    tbody.innerHTML = "";
    pagination.innerHTML = "";

    const params = new URLSearchParams({ page, page_size: pageSize });
    if (typeSelect.value) params.set("resource_type", typeSelect.value);

    try {
      const data = await withLoading(tbody.closest("table"), () =>
        apiFetch(`/voided-records?${params.toString()}`)
      );

      if (data.items.length === 0) {
        renderEmpty(
          tbody,
          columnCount(tbody.closest("table")),
          "Bekor qilingan yozuvlar yo'q"
        );
      }

      data.items.forEach((record) => {
        const tr = document.createElement("tr");
        tr.innerHTML = `
          <td>${escapeHtml(record.resource_label)}</td>
          <td>${escapeHtml(record.summary)}</td>
          <td>${formatDate(record.date)}</td>
          <td class="num">${record.amount != null ? formatMoney(record.amount) : "—"}</td>
          <td>${formatDateTime(record.voided_at)}</td>
          <td>${record.voided_by_name ? escapeHtml(record.voided_by_name) : '<span class="muted">—</span>'}</td>
          <td class="actions-cell">
            <button class="secondary restore-btn" data-type="${record.resource_type}" data-id="${record.id}">Tiklash</button>
            <button class="danger delete-btn" data-type="${record.resource_type}" data-id="${record.id}">O'chirish</button>
          </td>
        `;
        tbody.appendChild(tr);
      });

      tbody.querySelectorAll(".restore-btn").forEach((btn) => {
        btn.addEventListener("click", () => restoreRecord(btn.dataset.type, btn.dataset.id));
      });
      tbody.querySelectorAll(".delete-btn").forEach((btn) => {
        btn.addEventListener("click", () => deleteRecord(btn.dataset.type, btn.dataset.id));
      });

      pagination.innerHTML = `
        <button class="secondary" id="prev-page" ${page <= 1 ? "disabled" : ""}>Oldingi</button>
        <span>${paginationLabel(data)}</span>
        <button class="secondary" id="next-page" ${page >= data.pages ? "disabled" : ""}>Keyingi</button>
      `;
      const prevBtn = document.getElementById("prev-page");
      const nextBtn = document.getElementById("next-page");
      if (prevBtn) prevBtn.addEventListener("click", () => { page -= 1; loadVoided(); });
      if (nextBtn) nextBtn.addEventListener("click", () => { page += 1; loadVoided(); });
    } catch (err) {
      showError(errorContainer, err.detail || err.message || "Bekor qilingan yozuvlarni yuklashda xatolik");
    }
  }

  document.getElementById("voided-filter-form").addEventListener("submit", (event) => {
    event.preventDefault();
    page = 1;
    loadVoided();
  });

  loadVoided();
})();
