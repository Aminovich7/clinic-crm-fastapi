(async function () {
  const user = await initPage({ allowedRoles: ["superadmin", "manager"] });
  if (!user) return;

  const canDelete = user.role === "superadmin";

  const errorContainer = document.getElementById("error-container");
  const successContainer = document.getElementById("success-container");
  const tbody = document.getElementById("staff-tbody");
  const pagination = document.getElementById("pagination");
  const formCard = document.getElementById("form-card");
  const staffForm = document.getElementById("staff-form");
  const addBtn = document.getElementById("add-staff-btn");
  const cancelBtn = document.getElementById("cancel-form-btn");
  const formTitle = document.getElementById("form-title");
  const roleSelect = document.getElementById("role");
  const specialtyField = document.getElementById("specialty-field");
  const fixedSalaryField = document.getElementById("fixed-salary-field");

  const roleLabels = { doctor: "Shifokor", nurse: "Hamshira", other: "Boshqa" };
  const statusLabels = { active: "Faol", inactive: "Nofaol" };

  let page = 1;
  const pageSize = 20;
  let searchTerm = "";
  let roleFilter = "";
  let statusFilter = "";

  addBtn.classList.remove("hidden");
  attachMoneyInput(document.getElementById("fixed_salary"));

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

  function updateRoleFields() {
    const isDoctor = roleSelect.value === "doctor";
    specialtyField.classList.toggle("hidden", false);
    fixedSalaryField.classList.toggle("hidden", isDoctor);
    document.getElementById("specialty").required = isDoctor;
    if (isDoctor) {
      document.getElementById("fixed_salary").value = "";
    }
  }

  roleSelect.addEventListener("change", updateRoleFields);

  function openForm(staff = null) {
    staffForm.reset();
    document.getElementById("staff-id").value = staff ? staff.id : "";
    document.getElementById("first_name").value = staff ? staff.first_name : "";
    document.getElementById("last_name").value = staff ? staff.last_name : "";
    roleSelect.value = staff ? staff.role : "doctor";
    document.getElementById("specialty").value = staff && staff.specialty ? staff.specialty : "";
    document.getElementById("fixed_salary").value = staff && staff.fixed_salary != null ? formatMoneyInputValue(staff.fixed_salary) : "";
    document.getElementById("hire_date").value = staff && staff.hire_date ? staff.hire_date : "";
    formTitle.textContent = staff ? "Ishchini tahrirlash" : "Ishchi qo'shish";
    updateRoleFields();
    formCard.classList.remove("hidden");
  }

  function closeForm() {
    formCard.classList.add("hidden");
    staffForm.reset();
  }

  addBtn.addEventListener("click", () => openForm());
  cancelBtn.addEventListener("click", closeForm);

  staffForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    clearMessages();

    const id = document.getElementById("staff-id").value;
    const role = roleSelect.value;
    const fixedSalaryValue = moneyInputValue(document.getElementById("fixed_salary"));

    const payload = {
      first_name: document.getElementById("first_name").value,
      last_name: document.getElementById("last_name").value,
      role,
      specialty: document.getElementById("specialty").value || null,
      fixed_salary: role === "doctor" ? null : (fixedSalaryValue ? fixedSalaryValue : null),
      hire_date: document.getElementById("hire_date").value || null,
    };

    try {
      const isUpdate = Boolean(id);
      if (isUpdate) {
        await apiFetch(`/staff/${id}`, { method: "PATCH", body: payload });
      } else {
        await apiFetch("/staff", { method: "POST", body: payload });
      }
      closeForm();
      await loadStaff();
      showSuccess(isUpdate ? "Ishchi ma'lumotlari yangilandi" : "Ishchi qo'shildi");
    } catch (err) {
      showError(errorContainer, err.detail || err.message || "Ishchini saqlashda xatolik yuz berdi");
    }
  });

  async function toggleStatus(id, activate) {
    clearMessages();
    try {
      await apiFetch(`/staff/${id}/${activate ? "activate" : "deactivate"}`, { method: "POST" });
      await loadStaff();
      showSuccess(activate ? "Ishchi faollashtirildi" : "Ishchi nofaollashtirildi");
    } catch (err) {
      showError(errorContainer, err.detail || err.message || "Holatni o'zgartirishda xatolik yuz berdi");
    }
  }

  async function deleteStaff(id) {
    if (!confirm("Ushbu ishchini o'chirasizmi? Bu amalni qaytarib bo'lmaydi.")) return;
    clearMessages();
    try {
      await apiFetch(`/staff/${id}`, { method: "DELETE" });
      await loadStaff();
      showSuccess("Ishchi o'chirildi");
    } catch (err) {
      showError(errorContainer, err.detail || err.message || "Ishchini o'chirishda xatolik yuz berdi");
    }
  }

  async function loadStaff() {
    clearMessages();
    tbody.innerHTML = "";
    pagination.innerHTML = "";

    const params = new URLSearchParams({ page, page_size: pageSize });
    if (searchTerm) params.set("search", searchTerm);
    if (roleFilter) params.set("role", roleFilter);
    if (statusFilter) params.set("status", statusFilter);

    try {
      const data = await withLoading(tbody.closest("table"), () => apiFetch(`/staff?${params.toString()}`));

      if (data.items.length === 0) {
        renderEmpty(tbody, columnCount(tbody.closest("table")), "Ma'lumot topilmadi");
      }
      data.items.forEach((staff) => {
        const tr = document.createElement("tr");
        const actions = [
          `<button class="secondary edit-btn" data-id="${staff.id}">Tahrirlash</button>`,
        ];
        if (staff.status === "active") {
          actions.push(`<button class="secondary deactivate-btn" data-id="${staff.id}">Nofaollashtirish</button>`);
        } else {
          actions.push(`<button class="secondary activate-btn" data-id="${staff.id}">Faollashtirish</button>`);
        }
        if (canDelete) {
          actions.push(`<button class="danger delete-btn" data-id="${staff.id}">O'chirish</button>`);
        }

        const detail = staff.role === "doctor"
          ? escapeHtml(staff.specialty || "—")
          : (staff.fixed_salary != null ? `${formatMoney(staff.fixed_salary)} so'm` : "—");

        tr.innerHTML = `
          <td>${escapeHtml(staff.last_name)} ${escapeHtml(staff.first_name)}</td>
          <td>${roleLabels[staff.role] || staff.role}</td>
          <td>${detail}</td>
          <td>${statusLabels[staff.status] || staff.status}</td>
          <td class="actions-cell">${actions.join("")}</td>
        `;
        tbody.appendChild(tr);
      });

      tbody.querySelectorAll(".edit-btn").forEach((btn) => {
        btn.addEventListener("click", () => {
          const staff = data.items.find((s) => String(s.id) === btn.dataset.id);
          openForm(staff);
        });
      });
      tbody.querySelectorAll(".activate-btn").forEach((btn) => {
        btn.addEventListener("click", () => toggleStatus(btn.dataset.id, true));
      });
      tbody.querySelectorAll(".deactivate-btn").forEach((btn) => {
        btn.addEventListener("click", () => toggleStatus(btn.dataset.id, false));
      });
      tbody.querySelectorAll(".delete-btn").forEach((btn) => {
        btn.addEventListener("click", () => deleteStaff(btn.dataset.id));
      });

      pagination.innerHTML = `
        <button class="secondary" id="prev-page" ${page <= 1 ? "disabled" : ""}>Oldingi</button>
        <span>${paginationLabel(data)}</span>
        <button class="secondary" id="next-page" ${page >= data.pages ? "disabled" : ""}>Keyingi</button>
      `;
      const prevBtn = document.getElementById("prev-page");
      const nextBtn = document.getElementById("next-page");
      if (prevBtn) prevBtn.addEventListener("click", () => { page -= 1; loadStaff(); });
      if (nextBtn) nextBtn.addEventListener("click", () => { page += 1; loadStaff(); });
    } catch (err) {
      showError(errorContainer, err.detail || err.message || "Ishchilar ro'yxatini yuklashda xatolik");
    }
  }

  document.getElementById("filter-form").addEventListener("submit", (event) => {
    event.preventDefault();
    searchTerm = document.getElementById("search").value.trim();
    roleFilter = document.getElementById("role-filter").value;
    statusFilter = document.getElementById("status-filter").value;
    page = 1;
    loadStaff();
  });

  loadStaff();
})();
