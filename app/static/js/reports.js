(async function () {
  const user = await initPage({ allowedRoles: ["superadmin", "manager"] });
  if (!user) return;

  const errorContainer = document.getElementById("error-container");
  const summaryEl = document.getElementById("report-summary");
  const doctorTbody = document.getElementById("doctor-tbody");
  const doctorThead = document.getElementById("doctor-thead");
  const dateFromInput = document.getElementById("date_from");
  const dateToInput = document.getElementById("date_to");
  const exportBtn = document.getElementById("export-btn");
  const chartCanvas = document.getElementById("report-chart");

  let activeReport = "total";
  let chart = null;

  const today = new Date();
  const firstOfMonth = new Date(today.getFullYear(), today.getMonth(), 1);
  dateToInput.value = today.toISOString().slice(0, 10);
  dateFromInput.value = firstOfMonth.toISOString().slice(0, 10);

  document.querySelectorAll(".report-tab-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      activeReport = btn.dataset.report;
      document.querySelectorAll(".report-tab-btn").forEach((b) => b.classList.toggle("active", b === btn));
      loadReport();
    });
  });

  function statCard(label, value) {
    const div = document.createElement("div");
    div.className = "stat-card";
    div.innerHTML = `<div class="label">${label}</div><div class="value">${formatMoney(value)}</div>`;
    return div;
  }

  const SUMMARY_FIELDS = {
    total: [
      ["Umumiy daromad", "total_income"],
      ["Shifokor ulushi", "total_doctor_share"],
      ["Xarajatlar", "total_expense"],
      ["Klinika foydasi", "total_clinic_profit"],
    ],
    consultations: [
      ["Umumiy daromad", "total_income"],
      ["Shifokor ulushi", "total_doctor_share"],
      ["Xarajatlar", "total_consultation_expense"],
      ["Klinika foydasi", "total_clinic_profit"],
    ],
    surgeries: [
      ["Umumiy daromad", "surgery_total_income"],
      ["Shifokor ulushi", "surgery_total_doctor_share"],
      ["Xarajatlar", "surgery_total_expense"],
      ["Klinika foydasi", "surgery_total_clinic_profit"],
    ],
    rooms: [
      ["Umumiy daromad", "room_total_income"],
      ["Shifokor ulushi", "room_total_doctor_share"],
      ["Klinika foydasi", "room_total_clinic_profit"],
    ],
  };

  const DOCTOR_SHARE_KEYS = {
    total: null,
    consultations: "doctor_shares",
    surgeries: "surgery_doctor_shares",
    rooms: "room_doctor_shares",
  };

  function renderChart(report) {
    const labels = [];
    const values = [];

    if (activeReport === "total") {
      labels.push("Ko'riklar", "Operatsiyalar", "Xonalar");
      values.push(
        Number(report.consultation_income),
        Number(report.surgery_income),
        Number(report.room_income)
      );
    } else {
      const key = DOCTOR_SHARE_KEYS[activeReport];
      (report[key] || []).forEach((entry) => {
        labels.push(entry.name);
        values.push(Number(entry.total_share));
      });
    }

    if (chart) {
      chart.destroy();
    }
    chart = new Chart(chartCanvas, {
      type: "bar",
      data: {
        labels,
        datasets: [
          {
            label: activeReport === "total" ? "Bo'limlar bo'yicha daromad" : "Shifokor ulushi",
            data: values,
            backgroundColor: "#2563eb",
          },
        ],
      },
      options: {
        responsive: true,
        plugins: { legend: { display: false } },
      },
    });
  }

  function renderDoctorTable(report) {
    doctorTbody.innerHTML = "";
    const key = DOCTOR_SHARE_KEYS[activeReport];
    if (!key) {
      doctorThead.parentElement.parentElement.classList.add("hidden");
      return;
    }
    doctorThead.parentElement.parentElement.classList.remove("hidden");
    (report[key] || []).forEach((entry) => {
      const tr = document.createElement("tr");
      tr.innerHTML = `<td>${entry.name}</td><td>${formatMoney(entry.total_share)}</td><td>${entry.count}</td>`;
      doctorTbody.appendChild(tr);
    });
  }

  async function loadReport() {
    errorContainer.innerHTML = "";
    summaryEl.innerHTML = "";

    const params = new URLSearchParams({
      date_from: dateFromInput.value,
      date_to: dateToInput.value,
    });

    try {
      const report = await apiFetch(`/reports/${activeReport}?${params.toString()}`);

      SUMMARY_FIELDS[activeReport].forEach(([label, field]) => {
        summaryEl.appendChild(statCard(label, report[field]));
      });

      renderDoctorTable(report);
      renderChart(report);
    } catch (err) {
      showError(errorContainer, err.detail || err.message || "Hisobotni yuklashda xatolik");
    }
  }

  exportBtn.addEventListener("click", async () => {
    const params = new URLSearchParams({
      date_from: dateFromInput.value,
      date_to: dateToInput.value,
      format: "xlsx",
    });
    try {
      await apiDownload(`/reports/${activeReport}?${params.toString()}`);
    } catch (err) {
      showError(errorContainer, err.detail || err.message || "Hisobotni eksport qilishda xatolik");
    }
  });

  document.getElementById("range-form").addEventListener("submit", (event) => {
    event.preventDefault();
    loadReport();
  });

  loadReport();
})();
