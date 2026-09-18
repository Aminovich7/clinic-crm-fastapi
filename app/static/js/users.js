(async function () {
  const user = await initPage({ allowedRoles: ["superadmin", "manager"] });
  if (!user) return;

  const isSuperadmin = user.role === "superadmin";
  const isManager = user.role === "manager";

  const errorContainer = document.getElementById("error-container");
  const successContainer = document.getElementById("success-container");

  // prefix -> Uzbek noun forms, since "manager"/"assistant" can't just be
  // capitalized like in English.
  const LABELS = {
    manager: { noun: "Menejer", article: "bu menejerni" },
    assistant: { noun: "Yordamchi", article: "bu yordamchini" },
  };

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

  // ---------------------------------------------------------------------
  // Generic list+create+edit+block/unblock wiring, shared by the Managers
  // and Assistants sections — they differ only in endpoint prefix and
  // which roles may create/edit/block (both call this with their own
  // config).
  // ---------------------------------------------------------------------
  function setupUserSection({ prefix, listEndpoint, canManage }) {
    const label = LABELS[prefix];
    const tbody = document.getElementById(`${prefix}s-tbody`);
    const pagination = document.getElementById(`${prefix}s-pagination`);
    const formCard = document.getElementById(`${prefix}-form-card`);
    const form = document.getElementById(`${prefix}-form`);
    const addBtn = document.getElementById(`${prefix}-add-btn`);
    const cancelBtn = document.getElementById(`${prefix}-cancel-btn`);
    const formTitle = document.getElementById(`${prefix}-form-title`);
    const passwordNote = document.getElementById(`${prefix}-password-note`);
    const idInput = document.getElementById(`${prefix}-id`);
    const usernameInput = document.getElementById(`${prefix}-username`);
    const fullNameInput = document.getElementById(`${prefix}-full-name`);
    const passwordInput = document.getElementById(`${prefix}-password`);

    let page = 1;
    const pageSize = 20;

    if (!canManage) {
      addBtn.classList.add("hidden");
    }

    passwordNote.textContent =
      "Mavjud hisobni tahrirlashda har doim yangi parol kiritish talab qilinadi (kamida 8 belgi) — bu backend menejer/yordamchi ma'lumotlarini qisman yangilashni qo'llab-quvvatlamaydi.";

    function openForm(person = null) {
      form.reset();
      idInput.value = person ? person.id : "";
      usernameInput.value = person ? person.username : "";
      fullNameInput.value = person ? person.full_name : "";
      formTitle.textContent = person ? `${label.noun}ni tahrirlash` : `${label.noun} qo'shish`;
      formCard.classList.remove("hidden");
    }

    function closeForm() {
      formCard.classList.add("hidden");
      form.reset();
    }

    addBtn.addEventListener("click", () => openForm());
    cancelBtn.addEventListener("click", closeForm);

    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      clearMessages();

      const id = idInput.value;
      const payload = {
        username: usernameInput.value,
        full_name: fullNameInput.value,
        password: passwordInput.value,
      };

      try {
        const isUpdate = Boolean(id);
        if (isUpdate) {
          await apiFetch(`${listEndpoint}/${id}`, { method: "PATCH", body: payload });
        } else {
          await apiFetch(listEndpoint, { method: "POST", body: payload });
        }
        closeForm();
        await loadList();
        showSuccess(isUpdate ? `${label.noun} ma'lumotlari yangilandi` : `${label.noun} qo'shildi`);
      } catch (err) {
        showError(errorContainer, err.detail || err.message || `${label.noun}ni saqlashda xatolik`);
      }
    });

    async function setStatus(id, action) {
      const question =
        action === "block"
          ? `${label.article} bloklaysizmi?`
          : `${label.article} blokdan chiqarasizmi?`;
      if (!confirm(question)) return;
      clearMessages();
      try {
        await apiFetch(`${listEndpoint}/${id}/${action}`, { method: "POST" });
        await loadList();
        showSuccess(action === "block" ? `${label.noun} bloklandi` : `${label.noun} blokdan chiqarildi`);
      } catch (err) {
        const failMsg =
          action === "block" ? `${label.noun}ni bloklashda xatolik` : `${label.noun}ni blokdan chiqarishda xatolik`;
        showError(errorContainer, err.detail || err.message || failMsg);
      }
    }

    async function loadList() {
      clearMessages();
      tbody.innerHTML = "";
      pagination.innerHTML = "";

      const params = new URLSearchParams({ page, page_size: pageSize });
      try {
        const data = await withLoading(tbody.closest("table"), () => apiFetch(`${listEndpoint}?${params.toString()}`));

        if (data.items.length === 0) {
          renderEmpty(tbody, columnCount(tbody.closest("table")), "Ma'lumot topilmadi");
        }
        data.items.forEach((person) => {
          const tr = document.createElement("tr");
          const isBlocked = person.status === "blocked";
          const actions = [];
          if (canManage) {
            actions.push(`<button class="secondary edit-btn" data-id="${person.id}">Tahrirlash</button>`);
            if (isBlocked) {
              actions.push(`<button class="secondary unblock-btn" data-id="${person.id}">Blokdan chiqarish</button>`);
            } else {
              actions.push(`<button class="danger block-btn" data-id="${person.id}">Bloklash</button>`);
            }
          }
          tr.innerHTML = `
            <td>${escapeHtml(person.username)}</td>
            <td>${escapeHtml(person.full_name)}</td>
            <td>${isBlocked ? "bloklangan" : "faol"}</td>
            <td class="actions-cell">${actions.join("")}</td>
          `;
          tbody.appendChild(tr);
        });

        tbody.querySelectorAll(".edit-btn").forEach((btn) => {
          btn.addEventListener("click", () => {
            const person = data.items.find((p) => String(p.id) === btn.dataset.id);
            openForm(person);
          });
        });
        tbody.querySelectorAll(".block-btn").forEach((btn) => {
          btn.addEventListener("click", () => setStatus(btn.dataset.id, "block"));
        });
        tbody.querySelectorAll(".unblock-btn").forEach((btn) => {
          btn.addEventListener("click", () => setStatus(btn.dataset.id, "unblock"));
        });

        pagination.innerHTML = `
          <button class="secondary" id="${prefix}-prev-page" ${page <= 1 ? "disabled" : ""}>Oldingi</button>
          <span>${paginationLabel(data)}</span>
          <button class="secondary" id="${prefix}-next-page" ${page >= data.pages ? "disabled" : ""}>Keyingi</button>
        `;
        const prevBtn = document.getElementById(`${prefix}-prev-page`);
        const nextBtn = document.getElementById(`${prefix}-next-page`);
        if (prevBtn) prevBtn.addEventListener("click", () => { page -= 1; loadList(); });
        if (nextBtn) nextBtn.addEventListener("click", () => { page += 1; loadList(); });
      } catch (err) {
        showError(errorContainer, err.detail || err.message || `${label.noun}lar ro'yxatini yuklashda xatolik`);
      }
    }

    loadList();
  }

  // ---------------------------------------------------------------------
  // Managers section — superadmin only (matches create/block/unblock's
  // require_roles(SUPERADMIN) gate in app/users/router.py).
  // ---------------------------------------------------------------------
  if (isSuperadmin) {
    document.getElementById("managers-section").classList.remove("hidden");
    setupUserSection({
      prefix: "manager",
      listEndpoint: "/users/managers",
      canManage: true,
    });
  }

  // ---------------------------------------------------------------------
  // Assistants section — superadmin and manager (matches
  // require_roles(SUPERADMIN, MANAGER) on every assistant endpoint).
  // ---------------------------------------------------------------------
  if (isSuperadmin || isManager) {
    document.getElementById("assistants-section").classList.remove("hidden");
    setupUserSection({
      prefix: "assistant",
      listEndpoint: "/users/assistants",
      canManage: true,
    });
  }

  // ---------------------------------------------------------------------
  // My account — superadmin edits via PATCH /users/superadmin (username/
  // password, both optional — blank means "leave unchanged"). A manager
  // edits their own row via PATCH /users/managers/{own id}, which requires
  // all three fields (username/full_name/password) since that endpoint has
  // no partial-update schema — same as the Managers section's edit form.
  // ---------------------------------------------------------------------
  const accountSection = document.getElementById("account-section");
  const accountForm = document.getElementById("account-form");
  const accountUsername = document.getElementById("account-username");
  const accountFullName = document.getElementById("account-full-name");
  const accountFullNameField = document.getElementById("account-full-name-field");
  const accountPassword = document.getElementById("account-password");
  const accountNote = document.getElementById("account-note");

  accountSection.classList.remove("hidden");
  accountUsername.value = user.username;

  if (isSuperadmin) {
    accountFullNameField.classList.add("hidden");
    accountFullName.required = false;
    accountUsername.required = false;
    accountPassword.required = false;
    accountNote.textContent = "O'zgartirmoqchi bo'lmagan maydonni bo'sh qoldiring.";
  } else {
    accountFullNameField.classList.remove("hidden");
    accountFullName.value = user.full_name;
    accountFullName.required = true;
    accountUsername.required = true;
    accountPassword.required = true;
    accountNote.textContent =
      "Har bir saqlashda barcha maydonlar, jumladan parol ham to'ldirilishi kerak — faqat ismni o'zgartirsangiz ham parolni kiriting.";
  }

  accountForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    clearMessages();

    try {
      if (isSuperadmin) {
        await apiFetch("/users/superadmin", {
          method: "PATCH",
          body: {
            superadmin_username: accountUsername.value || null,
            superadmin_password: accountPassword.value || null,
          },
        });
      } else {
        await apiFetch(`/users/managers/${user.id}`, {
          method: "PATCH",
          body: {
            username: accountUsername.value,
            full_name: accountFullName.value,
            password: accountPassword.value,
          },
        });
      }
      accountPassword.value = "";
      showSuccess("Ma'lumotlaringiz yangilandi. Boshqa qurilmalarda qayta kirishga to'g'ri kelishi mumkin.");
    } catch (err) {
      showError(errorContainer, err.detail || err.message || "Ma'lumotlaringizni yangilashda xatolik");
    }
  });
})();
