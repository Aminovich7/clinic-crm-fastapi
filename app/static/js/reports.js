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
  const doctorSelectCard = document.getElementById("doctor-select-card");
  const doctorSelect = document.getElementById("report-doctor-select");

  let activeReport = "total";
  let chart = null;

  const today = new Date();
  const firstOfMonth = new Date(today.getFullYear(), today.getMonth(), 1);
  dateToInput.value = today.toISOString().slice(0, 10);
  dateFromInput.value = firstOfMonth.toISOString().slice(0, 10);

  async function loadDoctorSelectOptions() {
    try {
      const options = await apiFetch("/doctors/options");
      doctorSelect.innerHTML = '<option value="">— shifokorni tanlang —</option>';
      options.forEach((doc) => {
        const opt = document.createElement("option");
        opt.value = doc.id;
        opt.textContent = doc.name;
        doctorSelect.appendChild(opt);
      });
    } catch (err) {
      showError(errorContainer, err.detail || err.message || "Shifokorlar ro'yxatini yuklashda xatolik");
    }
  }

  document.querySelectorAll(".report-tab-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      activeReport = btn.dataset.report;
      document.querySelectorAll(".report-tab-btn").forEach((b) => b.classList.toggle("active", b === btn));
      doctorSelectCard.classList.toggle("hidden", activeReport !== "doctor");
      exportBtn.classList.toggle("hidden", activeReport === "doctor");
      loadReport();
    });
  });

  doctorSelect.addEventListener("change", () => {
    if (activeReport === "doctor") loadReport();
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

  const DOCTOR_TABLE_HEADER = "<tr><th>Shifokor</th><th>Ulush jami</th><th>Yozuvlar soni</th></tr>";

  function renderDoctorTable(report) {
    doctorThead.innerHTML = DOCTOR_TABLE_HEADER;
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

  // "Shifokor bo'yicha" tab: there's no single backend endpoint for a
  // doctor's combined earnings, so this pulls the three section reports
  // for the same date range (already broken down per doctor, per §3's
  // batch-loaded doctor_shares) and picks out the one doctor's row from
  // each — no new backend endpoint needed.
  async function loadDoctorReport() {
    const doctorId = doctorSelect.value;
    doctorThead.parentElement.parentElement.classList.remove("hidden");

    if (chart) {
      chart.destroy();
      chart = null;
    }

    if (!doctorId) {
      doctorThead.innerHTML = DOCTOR_TABLE_HEADER;
      doctorTbody.innerHTML = "";
      summaryEl.innerHTML = '<p class="muted">Hisobotni ko\'rish uchun shifokorni tanlang.</p>';
      return;
    }

    const params = new URLSearchParams({
      date_from: dateFromInput.value,
      date_to: dateToInput.value,
    });

    try {
      const [consultations, surgeries, rooms] = await Promise.all([
        apiFetch(`/reports/consultations?${params.toString()}`),
        apiFetch(`/reports/surgeries?${params.toString()}`),
        apiFetch(`/reports/rooms?${params.toString()}`),
      ]);

      const findShare = (list) => (list || []).find((e) => String(e.doctor_id) === doctorId);
      const cEntry = findShare(consultations.doctor_shares);
      const sEntry = findShare(surgeries.surgery_doctor_shares);
      const rEntry = findShare(rooms.room_doctor_shares);

      const cShare = Number(cEntry?.total_share || 0);
      const sShare = Number(sEntry?.total_share || 0);
      const rShare = Number(rEntry?.total_share || 0);
      const cCount = cEntry?.count || 0;
      const sCount = sEntry?.count || 0;
      const rCount = rEntry?.count || 0;

      summaryEl.appendChild(statCard("Ko'riklardan ulush", cShare));
      summaryEl.appendChild(statCard("Operatsiyalardan ulush", sShare));
      summaryEl.appendChild(statCard("Xonalardan ulush", rShare));
      summaryEl.appendChild(statCard("Jami ulush", cShare + sShare + rShare));

      doctorThead.innerHTML = "<tr><th>Bo'lim</th><th>Ulush</th><th>Yozuvlar soni</th></tr>";
      doctorTbody.innerHTML = "";
      [
        ["Ko'riklar", cShare, cCount],
        ["Operatsiyalar", sShare, sCount],
        ["Xonalar", rShare, rCount],
      ].forEach(([label, share, count]) => {
        const tr = document.createElement("tr");
        tr.innerHTML = `<td>${label}</td><td>${formatMoney(share)}</td><td>${count}</td>`;
        doctorTbody.appendChild(tr);
      });

      chart = new Chart(chartCanvas, {
        type: "bar",
        data: {
          labels: ["Ko'riklar", "Operatsiyalar", "Xonalar"],
          datasets: [{ label: "Shifokor ulushi", data: [cShare, sShare, rShare], backgroundColor: "#2563eb" }],
        },
        options: { responsive: true, plugins: { legend: { display: false } } },
      });
    } catch (err) {
      showError(errorContainer, err.detail || err.message || "Shifokor hisobotini yuklashda xatolik");
    }
  }

  async function loadReport() {
    errorContainer.innerHTML = "";
    summaryEl.innerHTML = "";

    if (activeReport === "doctor") {
      await loadDoctorReport();
      return;
    }

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

  await loadDoctorSelectOptions();
  loadReport();
})();
