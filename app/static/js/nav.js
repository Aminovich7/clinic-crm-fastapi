// Shared nav bootstrap: verifies auth, builds the role-aware nav, wires
// the logout button. Called by every authenticated page after its own
// data-loading logic is set up.

const NAV_LINKS = [
  { href: "/dashboard", label: "Boshqaruv paneli", roles: ["superadmin", "manager"] },
  { href: "/receipts", label: "Kvitansiyalar", roles: ["superadmin", "manager", "assistant"] },
  { href: "/reports", label: "Hisobotlar", roles: ["superadmin", "manager"] },
  { href: "/staff-page", label: "Ishchilar", roles: ["superadmin", "manager"] },
  { href: "/navbatchilik-page", label: "Navbatchilik", roles: ["superadmin", "manager"] },
  { href: "/salary-page", label: "Oyliklar", roles: ["superadmin", "manager"] },
  { href: "/pharmacy-page", label: "Dorixona", roles: ["superadmin", "manager"] },
  { href: "/expenses-page", label: "Boshqa harajatlar", roles: ["superadmin", "manager"] },
  { href: "/users-page", label: "Foydalanuvchilar", roles: ["superadmin", "manager"] },
  { href: "/audit-log", label: "Audit jurnali", roles: ["superadmin"] },
  { href: "/settings", label: "Sozlamalar", roles: ["superadmin"] },
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

  const nav = document.getElementById("mainnav");
  if (nav) {
    nav.innerHTML = "";
    const currentPath = window.location.pathname;
    NAV_LINKS.filter((link) => link.roles.includes(user.role)).forEach((link) => {
      const a = document.createElement("a");
      a.href = link.href;
      a.textContent = link.label;
      if (link.href === currentPath) {
        a.classList.add("active");
      }
      nav.appendChild(a);
    });
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

function showError(container, message) {
  container.innerHTML = "";
  const box = document.createElement("div");
  box.className = "error-box";
  box.textContent = message;
  container.appendChild(box);
}

function paginationLabel(data) {
  return `${data.page}-sahifa, ${Math.max(data.pages, 1)} tadan (jami ${data.total})`;
}
