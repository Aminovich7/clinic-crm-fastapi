// Shared nav bootstrap: verifies auth, builds the role-aware nav, wires
// the logout button. Called by every authenticated page after its own
// data-loading logic is set up.

// Nav is grouped so that eleven links stay scannable. A flat row of eleven
// needed ~1590px of header and silently wrapped onto a second and third row
// on any laptop-sized screen; a grouped sidebar also separates the pages used
// a hundred times a day from the ones touched twice a year.
const NAV_GROUPS = [
  {
    label: "Umumiy",
    links: [
      { href: "/dashboard", label: "Boshqaruv paneli", roles: ["superadmin", "manager"] },
      { href: "/reports", label: "Hisobotlar", roles: ["superadmin", "manager"] },
      { href: "/salary-page", label: "Oyliklar", roles: ["superadmin", "manager"] },
      { href: "/pharmacy-page", label: "Dorixona", roles: ["superadmin", "manager"] },
    ],
  },
  {
    label: "Asosiy",
    links: [
      { href: "/receipts", label: "Kvitansiyalar", roles: ["superadmin", "manager", "assistant"] },
      { href: "/navbatchilik-page", label: "Navbatchilik", roles: ["superadmin", "manager"] },
      { href: "/expenses-page", label: "Boshqa harajatlar", roles: ["superadmin", "manager"] },
      { href: "/staff-page", label: "Ishchilar", roles: ["superadmin", "manager"] },
    ],
  },
  {
    label: "Tizim",
    links: [
      { href: "/users-page", label: "Foydalanuvchilar", roles: ["superadmin", "manager"] },
      { href: "/audit-log", label: "Bekor qilingan yozuvlar", roles: ["superadmin"] },
      { href: "/settings", label: "Sozlamalar", roles: ["superadmin"] },
    ],
  },
];

const ROLE_LABELS = {
  superadmin: "bosh administrator",
  manager: "menejer",
  assistant: "yordamchi",
};

// Where a role lands when it hits a page it's not allowed to see.
// Assistants have no dashboard, so "/dashboard" can't be the universal
// fallback anymore — each role goes to the first page it's actually
// allowed to use.
const ROLE_HOME = {
  superadmin: "/dashboard",
  manager: "/dashboard",
  assistant: "/receipts",
};

async function initPage({ allowedRoles = null } = {}) {
  const user = await requireAuth();
  if (!user) {
    return null;
  }

  if (allowedRoles && !allowedRoles.includes(user.role)) {
    window.location.href = ROLE_HOME[user.role] || "/receipts";
    return null;
  }

  // Each page template supplies its own <h1>; hoist it into the sticky top
  // bar so every screen gets a consistent page header without editing all
  // twelve templates.
  const titleEl = document.getElementById("page-title");
  const pageHeading = document.querySelector("main.container > h1");
  if (titleEl && pageHeading) {
    titleEl.textContent = pageHeading.textContent;
    pageHeading.remove();
  } else if (titleEl) {
    titleEl.textContent = document.title.split("—")[0].trim();
  }

  const nav = document.getElementById("mainnav");
  const currentPath = window.location.pathname;
  let visibleLinkCount = 0;

  if (nav) {
    nav.innerHTML = "";
    NAV_GROUPS.forEach((group) => {
      const links = group.links.filter((link) => link.roles.includes(user.role));
      if (links.length === 0) return; // a group with nothing in it doesn't render

      const section = document.createElement("div");
      section.className = "nav-group";

      const label = document.createElement("div");
      label.className = "nav-group-label";
      label.textContent = group.label;
      section.appendChild(label);

      links.forEach((link) => {
        const a = document.createElement("a");
        a.href = link.href;
        a.textContent = link.label;
        if (link.href === currentPath) {
          a.classList.add("active");
          a.setAttribute("aria-current", "page");
        }
        section.appendChild(a);
        visibleLinkCount += 1;
      });

      nav.appendChild(section);
    });
  }

  // A nav holding a single link pointing at the page you're already on is
  // pure chrome — assistants get the content area full-width instead.
  if (visibleLinkCount <= 1) {
    document.body.classList.add("no-sidebar");
  }

  const nameEl = document.getElementById("current-user-name");
  if (nameEl) {
    nameEl.textContent = `${user.full_name} (${ROLE_LABELS[user.role] || user.role})`;
  }

  const logoutBtn = document.getElementById("logout-btn");
  if (logoutBtn) {
    logoutBtn.addEventListener("click", () => logout());
  }

  return user;
}

function formatMoney(value) {
  const n = Number(value);
  if (Number.isNaN(n)) return value;
  return n.toLocaleString("en-US");
}

const UZ_MONTHS = [
  "Yanvar", "Fevral", "Mart", "Aprel", "May", "Iyun",
  "Iyul", "Avgust", "Sentabr", "Oktabr", "Noyabr", "Dekabr",
];

// Formats a pure calendar date ("YYYY-MM-DD", no time component) as
// "DD-MonthName-YYYY", reading the digits directly out of the string
// instead of going through Date() (which applies UTC-to-local conversion
// and can shift a date-only value onto the wrong calendar day for a
// viewer outside the clinic's timezone).
function formatDate(value) {
  if (!value) return "—";
  const match = String(value).match(/^(\d{4})-(\d{2})-(\d{2})/);
  if (!match) return value;
  const [, year, month, day] = match;
  return `${day}-${UZ_MONTHS[Number(month) - 1]}-${year}`;
}

// Formats a full timestamp as "DD-MonthName-YYYY HH:mm" in the viewer's
// local time zone (date and time both read from the same local
// conversion, so they never disagree with each other).
function formatDateTime(value) {
  if (!value) return "—";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return formatDate(value);
  const day = String(d.getDate()).padStart(2, "0");
  const month = UZ_MONTHS[d.getMonth()];
  const hh = String(d.getHours()).padStart(2, "0");
  const mm = String(d.getMinutes()).padStart(2, "0");
  return `${day}-${month}-${d.getFullYear()} ${hh}:${mm}`;
}

// Formats digits as a comma-grouped string while the user types into a
// money-amount input (e.g. "1000000" becomes "1,000,000"). Non-digit
// characters (including a comma the user typed themselves) are stripped
// first, so pasting a pre-formatted number works too.
function formatMoneyInputValue(raw) {
  const digits = String(raw).replace(/\D/g, "");
  if (!digits) return "";
  return Number(digits).toLocaleString("en-US");
}

// Wires a text input to live-format as comma-grouped digits while typing,
// preserving cursor position relative to the end of the value (simple and
// robust for money entry, where edits are almost always at the end).
function attachMoneyInput(input) {
  input.addEventListener("input", () => {
    const distanceFromEnd = input.value.length - input.selectionStart;
    input.value = formatMoneyInputValue(input.value);
    const pos = Math.max(0, input.value.length - distanceFromEnd);
    input.setSelectionRange(pos, pos);
  });
}

// Reads a money-amount input's raw digits (no commas) as a string, ready
// to send to the API. Returns "" if the field is empty.
function moneyInputValue(input) {
  return input.value.replace(/\D/g, "");
}

// Escapes free-text values (titles, comments, names) before they're
// interpolated into an innerHTML template string, so a value containing
// "<", ">", "&", quotes, etc. renders as literal text instead of being
// parsed as markup.
function escapeHtml(value) {
  if (value == null) return "";
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function showError(container, message) {
  container.innerHTML = "";
  const box = document.createElement("div");
  box.className = "error-box";
  box.textContent = message;
  container.appendChild(box);
}

// Renders a centered "nothing here" row so that a filter matching zero
// records is visibly distinct from a failed request or a half-loaded page.
// `colspan` should match the table's current column count — pass the same
// header array length the thead was built from.
function renderEmpty(tbody, colspan, message) {
  tbody.innerHTML = "";
  const tr = document.createElement("tr");
  tr.className = "table-empty";
  const td = document.createElement("td");
  td.colSpan = colspan;
  td.textContent = message || "Ma'lumot topilmadi";
  tr.appendChild(td);
  tbody.appendChild(tr);
}

// Dims a table (or any container) while its data is in flight, so lists fade
// rather than flashing empty and then repopulating.
function setLoading(element, isLoading) {
  if (!element) return;
  element.classList.toggle("is-loading", Boolean(isLoading));
}

// Runs an async load with the loading state applied for its duration. The
// `finally` matters: without it a failed request would leave the table dimmed
// and pointer-events:none forever.
async function withLoading(element, run) {
  setLoading(element, true);
  try {
    return await run();
  } finally {
    setLoading(element, false);
  }
}

// Column count for whichever table body is being rendered, read off the
// matching thead so the empty row always spans the full width.
function columnCount(tableEl) {
  if (!tableEl) return 1;
  const head = tableEl.querySelector("thead tr");
  return head ? head.children.length : 1;
}

// --- Voided-record actions ----------------------------------------------
// Restore and hard delete are superadmin-only and only ever apply to records
// that are already voided, so both buttons render together or not at all.

function canManageVoided(user) {
  return user.role === "superadmin";
}

// `extraAttrs` lets a page attach whatever it needs to identify the record
// (Kvitansiyalar passes data-kind, since one table serves three resources).
function voidedActionButtons(user, record, extraAttrs = "") {
  if (!canManageVoided(user) || !record.is_voided) return "";
  return (
    `<button class="secondary restore-btn" ${extraAttrs} data-id="${record.id}">Tiklash</button>` +
    `<button class="danger delete-btn" ${extraAttrs} data-id="${record.id}">O'chirish</button>`
  );
}

const RESTORE_CONFIRM =
  "Ushbu yozuvni tiklaysizmi? U yana hisobotlarga qo'shiladi.";

const DELETE_CONFIRM =
  "Ushbu yozuvni butunlay o'chirasizmi?\n\n" +
  "Bu amalni QAYTARIB BO'LMAYDI. Yozuv ma'lumotlar bazasidan butunlay " +
  "o'chiriladi va uning ma'lumotlari hech qayerda saqlanmaydi.";

// --- Calendar-month range shortcuts -------------------------------------
// Shared by every page with a date-range filter ("Joriy oy" / "O'tgan oy").
// Local calendar arithmetic only, with no UTC round-trip, so the range is
// the clinic's actual month regardless of the viewer's time zone.

// Formats a Date as the "YYYY-MM-DD" a <input type="date"> expects, reading
// the *local* calendar fields.
//
// Never use toISOString().slice(0, 10) for this. toISOString() converts to
// UTC first, and in Asia/Tashkent (UTC+5) local midnight is still the
// previous day in UTC — so `new Date(y, m, 1).toISOString().slice(0, 10)`
// yields the last day of the *previous* month, every time. That is exactly
// what the dashboard and Hisobotlar pages were sending as date_from, which
// quietly folded one extra day of the previous month into every "this month"
// figure on the page.
function toDateInputValue(d) {
  const pad = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

// offsetMonths=0 is the current month, -1 the previous one.
function firstAndLastOfMonth(offsetMonths) {
  const now = new Date();
  const first = new Date(now.getFullYear(), now.getMonth() + offsetMonths, 1);
  const last = new Date(now.getFullYear(), now.getMonth() + offsetMonths + 1, 0);
  return { from: toDateInputValue(first), to: toDateInputValue(last) };
}

// The default range both the dashboard and Hisobotlar open with: the 1st of
// the current month through today, inclusive.
function monthToDateRange() {
  const now = new Date();
  return {
    from: toDateInputValue(new Date(now.getFullYear(), now.getMonth(), 1)),
    to: toDateInputValue(now),
  };
}

// month is 1-indexed; day 0 of the "next" month rolls back to the last day
// of this one.
function daysInMonth(year, month) {
  return new Date(year, month, 0).getDate();
}

// "Davr: Sentabr 2026" when the range is exactly one calendar month,
// otherwise the explicit "Davr: 05-Sentabr-2026 — 18-Sentabr-2026".
function monthPeriodLabel(fromVal, toVal) {
  if (!fromVal || !toVal) return "";

  const [fromYear, fromMonth, fromDay] = fromVal.split("-").map(Number);
  const [toYear, toMonth, toDay] = toVal.split("-").map(Number);
  const isFullCalendarMonth =
    fromDay === 1 &&
    fromYear === toYear &&
    fromMonth === toMonth &&
    toDay === daysInMonth(toYear, toMonth);

  return isFullCalendarMonth
    ? `Davr: ${UZ_MONTHS[fromMonth - 1]} ${fromYear}`
    : `Davr: ${formatDate(fromVal)} — ${formatDate(toVal)}`;
}

// Wires the two shortcut buttons and keeps the visible period label in sync
// with whatever is actually in the date inputs — including ranges the user
// types by hand, so the label can never disagree with the query.
function attachMonthShortcuts({
  fromInput,
  toInput,
  currentBtn,
  previousBtn,
  labelEl,
  onApply,
}) {
  if (!fromInput || !toInput) return null;

  function refreshLabel() {
    if (labelEl) labelEl.textContent = monthPeriodLabel(fromInput.value, toInput.value);
  }

  function apply(offsetMonths) {
    const { from, to } = firstAndLastOfMonth(offsetMonths);
    fromInput.value = from;
    toInput.value = to;
    refreshLabel();
    if (onApply) onApply();
  }

  if (currentBtn) currentBtn.addEventListener("click", () => apply(0));
  if (previousBtn) previousBtn.addEventListener("click", () => apply(-1));
  fromInput.addEventListener("change", refreshLabel);
  toInput.addEventListener("change", refreshLabel);
  refreshLabel();

  return { apply, refreshLabel };
}

// --- Exact money arithmetic ---------------------------------------------
// The server computes every figure with Python's Decimal and ROUND_HALF_UP
// (app/finance/calculations.py). Doing the same sums in JS with floats and
// Math.round drifts: 0.1 + 0.2 problems aside, a product that lands exactly
// on .5 in decimal can land just below it in binary floating point and round
// the other way, so a receipt's on-screen preview could disagree with the
// report by 1 so'm. These helpers do the arithmetic in BigInt instead, which
// is exact, and round half-up away from zero exactly as Decimal does.

// Parses a decimal string ("1500", "12.50") into a BigInt scaled by 10^scale.
// "12.5" at scale 2 -> 1250n. Digits beyond `scale` are rounded half-up, the
// same way Postgres quantizes into Numeric(12,0)/Numeric(5,2) and the same
// way Decimal.quantize(ROUND_HALF_UP) does server-side — so a percent typed
// into the create form with more precision than the column holds previews
// the value that will actually be stored.
function toScaledBigInt(value, scale) {
  const text = String(value ?? "0").trim();
  const match = text.match(/^(-?)(\d*)(?:\.(\d*))?$/);
  if (!match) return 0n;
  const [, sign, whole, fraction = ""] = match;

  const kept = (fraction + "0".repeat(scale)).slice(0, scale);
  const dropped = fraction.slice(scale);

  let result = BigInt((whole || "0") + kept);
  if (dropped && dropped[0] >= "5") {
    result += 1n;
  }
  return sign === "-" ? -result : result;
}

// Divides two BigInts, rounding half away from zero — Decimal's ROUND_HALF_UP.
function roundHalfUpDiv(numerator, denominator) {
  const negative = numerator < 0n;
  const magnitude = negative ? -numerator : numerator;
  const quotient = (magnitude * 2n + denominator) / (2n * denominator);
  return negative ? -quotient : quotient;
}

// money((base * percent) / 100) from app/finance/calculations.py, exactly.
// `base` is a whole-so'm amount; `percent` may carry two decimals.
function percentageOf(base, percent) {
  const baseUnits = toScaledBigInt(base, 0);
  const percentBasisPoints = toScaledBigInt(percent, 2);
  return roundHalfUpDiv(baseUnits * percentBasisPoints, 10000n);
}

function paginationLabel(data) {
  return `${data.page}-sahifa, ${Math.max(data.pages, 1)} tadan (jami ${data.total})`;
}
