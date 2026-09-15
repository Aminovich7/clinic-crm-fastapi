(async function () {
  const user = await initPage();
  if (!user) return;

  const canManage = user.role === "superadmin" || user.role === "manager";
  const canDelete = user.role === "superadmin";

  const errorContainer = document.getElementById("error-container");
  const successContainer = document.getElementById("success-container");
  const tbody = document.getElementById("doctors-tbody");
  const pagination = document.getElementById("pagination");
  const formCard = document.getElementById("form-card");
  const doctorForm = document.getElementById("doctor-form");
  const addBtn = document.getElementById("add-doctor-btn");
  const cancelBtn = document.getElementById("cancel-form-btn");
  const formTitle = document.getElementById("form-title");

  let page = 1;
  const pageSize = 20;
  let searchTerm = "";

  if (canManage) {
    addBtn.classList.remove("hidden");
  }

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

  function openForm(doctor = null) {
    doctorForm.reset();
    document.getElementById("doctor-id").value = doctor ? doctor.id : "";
    document.getElementById("first_name").value = doctor ? doctor.first_name : "";
    document.getElementById("last_name").value = doctor ? doctor.last_name : "";
    document.getElementById("specialty").value = doctor ? doctor.specialty : "";
    formTitle.textContent = doctor ? "Shifokorni tahrirlash" : "Shifokor qo'shish";
    formCard.classList.remove("hidden");
  }

  function closeForm() {
    formCard.classList.add("hidden");
    doctorForm.reset();
  }

  addBtn.addEventListener("click", () => openForm());
  cancelBtn.addEventListener("click", closeForm);

  doctorForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    clearMessages();

    const id = document.getElementById("doctor-id").value;
    const payload = {
      first_name: document.getElementById("first_name").value,
      last_name: document.getElementById("last_name").value,
      specialty: document.getElementById("specialty").value,
    };

    try {
      const isUpdate = Boolean(id);
      if (isUpdate) {
        await apiFetch(`/doctors/${id}`, { method: "PATCH", body: payload });
      } else {
        await apiFetch("/doctors", { method: "POST", body: payload });
      }
      closeForm();
      await loadDoctors();
      showSuccess(isUpdate ? "Shifokor ma'lumotlari yangilandi" : "Shifokor qo'shildi");
    } catch (err) {
      showError(errorContainer, err.detail || err.message || "Shifokorni saqlashda xatolik yuz berdi");
    }
  });

  async function deleteDoctor(id) {
    if (!confirm("Ushbu shifokorni o'chirasizmi? Bu amalni qaytarib bo'lmaydi.")) return;
    clearMessages();
    try {
      await apiFetch(`/doctors/${id}`, { method: "DELETE" });
      await loadDoctors();
      showSuccess("Shifokor o'chirildi");
    } catch (err) {
      showError(errorContainer, err.detail || err.message || "Shifokorni o'chirishda xatolik yuz berdi");
    }
  }

  async function loadDoctors() {
    clearMessages();
    tbody.innerHTML = "";
    pagination.innerHTML = "";

    const params = new URLSearchParams({ page, page_size: pageSize });
    if (searchTerm) params.set("search", searchTerm);

    try {
      const data = await apiFetch(`/doctors?${params.toString()}`);

      data.items.forEach((doctor) => {
        const tr = document.createElement("tr");
        const actions = [];
        if (canManage) {
          actions.push(`<button class="secondary edit-btn" data-id="${doctor.id}">Tahrirlash</button>`);
        }
        if (canDelete) {
          actions.push(`<button class="danger delete-btn" data-id="${doctor.id}">O'chirish</button>`);
        }
        tr.innerHTML = `
          <td>${doctor.last_name} ${doctor.first_name}</td>
          <td>${doctor.specialty}</td>
          <td class="actions-cell">${actions.join("")}</td>
        `;
        tbody.appendChild(tr);
      });

      tbody.querySelectorAll(".edit-btn").forEach((btn) => {
        btn.addEventListener("click", () => {
          const doctor = data.items.find((d) => String(d.id) === btn.dataset.id);
          openForm(doctor);
        });
      });
      tbody.querySelectorAll(".delete-btn").forEach((btn) => {
        btn.addEventListener("click", () => deleteDoctor(btn.dataset.id));
      });

      pagination.innerHTML = `
        <button class="secondary" id="prev-page" ${page <= 1 ? "disabled" : ""}>Oldingi</button>
        <span>${paginationLabel(data)}</span>
        <button class="secondary" id="next-page" ${page >= data.pages ? "disabled" : ""}>Keyingi</button>
      `;
      const prevBtn = document.getElementById("prev-page");
      const nextBtn = document.getElementById("next-page");
      if (prevBtn) prevBtn.addEventListener("click", () => { page -= 1; loadDoctors(); });
      if (nextBtn) nextBtn.addEventListener("click", () => { page += 1; loadDoctors(); });
    } catch (err) {
      showError(errorContainer, err.detail || err.message || "Shifokorlar ro'yxatini yuklashda xatolik");
    }
  }

  document.getElementById("search-form").addEventListener("submit", (event) => {
    event.preventDefault();
    searchTerm = document.getElementById("search").value.trim();
    page = 1;
    loadDoctors();
  });

  loadDoctors();
})();
