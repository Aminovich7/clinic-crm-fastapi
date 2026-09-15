(async function redirectIfLoggedIn() {
  const token = await getAccessToken().catch(() => null);
  if (token) {
    window.location.href = "/dashboard";
  }
})();

const form = document.getElementById("login-form");
const errorContainer = document.getElementById("error-container");
const loginBtn = document.getElementById("login-btn");

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  errorContainer.innerHTML = "";
  loginBtn.disabled = true;

  const username = document.getElementById("username").value;
  const password = document.getElementById("password").value;

  try {
    const response = await fetch("/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams({ username, password }),
    });

    if (!response.ok) {
      let detail = "Kirishda xatolik yuz berdi";
      if (response.status === 429) {
        detail = "Juda ko'p urinish. Iltimos, bir daqiqa kutib, qayta urinib ko'ring.";
      } else {
        const payload = await response.json().catch(() => null);
        if (payload && payload.detail) detail = payload.detail;
      }
      throw new Error(detail);
    }

    const data = await response.json();
    setRefreshToken(data.refresh_token);
    window.location.href = "/dashboard";
  } catch (err) {
    const box = document.createElement("div");
    box.className = "error-box";
    box.textContent = err.message || "Kirishda xatolik yuz berdi";
    errorContainer.appendChild(box);
  } finally {
    loginBtn.disabled = false;
  }
});
