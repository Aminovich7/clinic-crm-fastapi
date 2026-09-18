(async function () {
  const user = await initPage({ allowedRoles: ["superadmin", "manager"] });
  if (!user) return;

  const dateFromInput = document.getElementById("date_from");
  const dateToInput = document.getElementById("date_to");
  const errorContainer = document.getElementById("error-container");
  const summaryCards = document.getElementById("summary-cards");
  const sectionCards = document.getElementById("section-cards");
  const payrollExpenseCards = document.getElementById("payroll-expense-cards");

  // Local calendar arithmetic via monthToDateRange() (nav.js) — see the note
  // on toDateInputValue() for why toISOString() must not be used here.
  const defaultRange = monthToDateRange();
  dateFromInput.value = defaultRange.from;
  dateToInput.value = defaultRange.to;

  // `variant` picks the accent rail + figure color (see .stat-card--* in
  // style.css). Colouring by meaning rather than decoration: income reads
  // blue, money leaving the clinic amber, what's left green.
  function statCard(label, value, variant) {
    const div = document.createElement("div");
    div.className = `stat-card${variant ? ` stat-card--${variant}` : ""}`;
    div.innerHTML =
      `<div class="label">${label}</div>` +
      `<div class="value">${formatMoney(value)}<span class="unit">so'm</span></div>`;
    return div;
  }

  async function loadReport() {
    errorContainer.innerHTML = "";
    summaryCards.innerHTML = "";
    sectionCards.innerHTML = "";
    payrollExpenseCards.innerHTML = "";

    const params = new URLSearchParams({
      date_from: dateFromInput.value,
      date_to: dateToInput.value,
    });

    try {
      const [report, salaryTotal, expensesSummary] = await Promise.all([
        apiFetch(`/reports/total?${params.toString()}`),
        apiFetch(`/salary/total-paid?${params.toString()}`),
        apiFetch(`/expenses/summary?${params.toString()}`),
      ]);

      // Clinic profit leads the page — it's the figure the dashboard exists
      // to answer, so it gets the wide tinted hero card rather than sitting
      // fourth in a row of four identical tiles.
      const heroCard = statCard("Klinika foydasi", report.total_clinic_profit);
      heroCard.classList.add("stat-card--hero");
      summaryCards.appendChild(heroCard);
      summaryCards.appendChild(statCard("Umumiy daromad", report.total_income, "primary"));
      summaryCards.appendChild(statCard("Shifokor ulushi", report.total_doctor_share, "violet"));
      summaryCards.appendChild(statCard("Xarajatlar", report.total_expense, "warning"));

      sectionCards.appendChild(statCard("Ko'riklar daromadi", report.consultation_income, "primary"));
      sectionCards.appendChild(statCard("Operatsiyalar daromadi", report.surgery_income, "violet"));
      sectionCards.appendChild(statCard("Xonalar daromadi", report.room_income, "teal"));

      const incomeAfterSalary = Number(report.total_income) - Number(salaryTotal.total_paid);
      const incomeAfterAll = incomeAfterSalary - Number(expensesSummary.total_amount);

      payrollExpenseCards.appendChild(statCard("Jami ish haqi to'lovlari", salaryTotal.total_paid, "warning"));
      payrollExpenseCards.appendChild(statCard("Ish haqidan keyingi daromad", incomeAfterSalary, "primary"));
      payrollExpenseCards.appendChild(statCard("Jami boshqa harajatlar", expensesSummary.total_amount, "warning"));
      payrollExpenseCards.appendChild(statCard("Ish haqi va harajatlardan keyingi daromad", incomeAfterAll, "success"));
    } catch (err) {
      showError(errorContainer, err.detail || err.message || "Boshqaruv panelini yuklashda xatolik");
    }
  }

  document.getElementById("range-form").addEventListener("submit", (event) => {
    event.preventDefault();
    loadReport();
  });

  attachMonthShortcuts({
    fromInput: dateFromInput,
    toInput: dateToInput,
    currentBtn: document.getElementById("current-month-btn"),
    previousBtn: document.getElementById("previous-month-btn"),
    labelEl: document.getElementById("period-label"),
    onApply: loadReport,
  });

  loadReport();
})();
