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
