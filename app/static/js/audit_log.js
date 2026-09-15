(async function () {
  const user = await initPage({ allowedRoles: ["superadmin"] });
  if (!user) return;

  const errorContainer = document.getElementById("error-container");
  const tbody = document.getElementById("audit-tbody");
  const pagination = document.getElementById("pagination");

  let page = 1;
  const pageSize = 20;

  async function loadLogs() {
    errorContainer.innerHTML = "";
    tbody.innerHTML = "";
    pagination.innerHTML = "";

    const params = new URLSearchParams({ page, page_size: pageSize });
    const resourceType = document.getElementById("resource_type").value.trim();
    const resourceId = document.getElementById("resource_id").value.trim();
    const dateFrom = document.getElementById("date_from").value;
    const dateTo = document.getElementById("date_to").value;
    if (resourceType) params.set("resource_type", resourceType);
    if (resourceId) params.set("resource_id", resourceId);
    if (dateFrom) params.set("date_from", dateFrom);
    if (dateTo) params.set("date_to", dateTo);

    try {
      const data = await apiFetch(`/audit-logs?${params.toString()}`);
      data.items.forEach((log) => {
        const tr = document.createElement("tr");
        tr.innerHTML = `
          <td>${new Date(log.created_at).toLocaleString()}</td>
          <td>${log.actor_id ?? "tizim"}</td>
          <td>${log.action}</td>
          <td>${log.resource_type}</td>
          <td>${log.resource_id}</td>
        `;
        tbody.appendChild(tr);
      });

      pagination.innerHTML = `
        <button class="secondary" id="prev-page" ${page <= 1 ? "disabled" : ""}>Oldingi</button>
        <span>${paginationLabel(data)}</span>
        <button class="secondary" id="next-page" ${page >= data.pages ? "disabled" : ""}>Keyingi</button>
      `;
      const prevBtn = document.getElementById("prev-page");
      const nextBtn = document.getElementById("next-page");
      if (prevBtn) prevBtn.addEventListener("click", () => { page -= 1; loadLogs(); });
      if (nextBtn) nextBtn.addEventListener("click", () => { page += 1; loadLogs(); });
    } catch (err) {
      showError(errorContainer, err.detail || err.message || "Audit jurnalini yuklashda xatolik");
    }
  }

  document.getElementById("filter-form").addEventListener("submit", (event) => {
    event.preventDefault();
    page = 1;
    loadLogs();
  });

  loadLogs();
})();
