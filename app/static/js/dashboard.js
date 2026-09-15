(async function () {
  const user = await initPage();
  if (!user) return;

  const dateFromInput = document.getElementById("date_from");
  const dateToInput = document.getElementById("date_to");
  const errorContainer = document.getElementById("error-container");
  const summaryCards = document.getElementById("summary-cards");
  const sectionCards = document.getElementById("section-cards");

  const today = new Date();
  const firstOfMonth = new Date(today.getFullYear(), today.getMonth(), 1);
  dateToInput.value = today.toISOString().slice(0, 10);
  dateFromInput.value = firstOfMonth.toISOString().slice(0, 10);

  function statCard(label, value) {
    const div = document.createElement("div");
    div.className = "stat-card";
    div.innerHTML = `<div class="label">${label}</div><div class="value">${formatMoney(value)}</div>`;
    return div;
  }

  async function loadReport() {
    errorContainer.innerHTML = "";
    summaryCards.innerHTML = "";
    sectionCards.innerHTML = "";

    const params = new URLSearchParams({
      date_from: dateFromInput.value,
      date_to: dateToInput.value,
    });

    try {
      const report = await apiFetch(`/reports/total?${params.toString()}`);

      summaryCards.appendChild(statCard("Umumiy daromad", report.total_income));
      summaryCards.appendChild(statCard("Shifokor ulushi", report.total_doctor_share));
      summaryCards.appendChild(statCard("Xarajatlar", report.total_expense));
      summaryCards.appendChild(statCard("Klinika foydasi", report.total_clinic_profit));

      sectionCards.appendChild(statCard("Ko'riklar daromadi", report.consultation_income));
      sectionCards.appendChild(statCard("Operatsiyalar daromadi", report.surgery_income));
      sectionCards.appendChild(statCard("Xonalar daromadi", report.room_income));
    } catch (err) {
      showError(errorContainer, err.detail || err.message || "Boshqaruv panelini yuklashda xatolik");
    }
  }

  document.getElementById("range-form").addEventListener("submit", (event) => {
    event.preventDefault();
    loadReport();
  });

  loadReport();
})();
