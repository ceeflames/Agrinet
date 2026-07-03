document.addEventListener("DOMContentLoaded", () => {

  // ====== AUTH STATE ======
  const token = localStorage.getItem("token");
  const role = localStorage.getItem("role");
  const name = localStorage.getItem("name");

  function updateAuthUI() {
    const authButtons = document.getElementById("auth-buttons");
    const sellerCard = document.getElementById("seller-reg-content");
    if (!authButtons || !sellerCard) return;

    if (token && name) {
      authButtons.innerHTML = `
        <span class="user-greeting">👤 ${name}</span>
        <button class="btn-dashboard" onclick="window.location.href='/dashboard'">Dashboard</button>
        <button class="btn-logout" onclick="logout()">Log Out</button>
        <button>🛒 <span id="cart-count">0</span></button>
      `;
      sellerCard.innerHTML = role === "farmer"
        ? `<div class="seller-reg-notice"><p>✅ Registered as a farmer.</p><a href="/dashboard">List produce →</a></div>`
        : `<div class="seller-reg-notice"><p>Want to sell?</p><a href="/signup">Register as Farmer →</a></div>`;
      const investNotice = document.getElementById("invest-auth-notice");
      const investForm = document.getElementById("invest-form");
      const vetNotice = document.getElementById("vet-auth-notice");
      const vetForm = document.getElementById("vet-form");
      if (investNotice) investNotice.style.display = "none";
      if (investForm) investForm.style.display = "block";
      if (vetNotice) vetNotice.style.display = "none";
      if (vetForm) vetForm.style.display = "block";
    } else {
      authButtons.innerHTML = `
        <button class="btn-login" onclick="window.location.href='/login'">Log In</button>
        <button class="btn-signup" onclick="window.location.href='/signup'">Sign Up</button>
        <button>🛒 <span id="cart-count">0</span></button>
      `;
      sellerCard.innerHTML = `
        <div class="seller-reg-notice"><p>Want to sell on AgriNet?</p><a href="/signup">Create a Farmer Account →</a></div>
        <small style="color:#6b7280;display:block;margin-top:0.5rem">KYC & verification required.</small>
      `;
      const investNotice = document.getElementById("invest-auth-notice");
      const investForm = document.getElementById("invest-form");
      const vetNotice = document.getElementById("vet-auth-notice");
      const vetForm = document.getElementById("vet-form");
      if (investNotice) investNotice.style.display = "block";
      if (investForm) investForm.style.display = "none";
      if (vetNotice) vetNotice.style.display = "block";
      if (vetForm) vetForm.style.display = "none";
    }
  }

  window.logout = function () {
    localStorage.clear();
    window.location.href = "/";
  };

  // ====== TABS ======
  document.querySelectorAll(".tab-button").forEach(btn => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".tab-button").forEach(b => b.classList.remove("active"));
      document.querySelectorAll(".tab-content").forEach(c => c.classList.remove("active"));
      btn.classList.add("active");
      document.getElementById(btn.dataset.target).classList.add("active");
    });
  });

  window.toggleInternational = function () {
    const foreign = document.getElementById("foreign-breeds");
    const local = document.getElementById("local-feeds");
    const btn = document.getElementById("intl-toggle");
    if (!foreign || !local || !btn) return;
    const showingLocal = local.style.display !== "none";
    if (showingLocal) {
      local.style.display = "none";
      foreign.style.display = "grid";
      btn.textContent = "← Back to Local Breeds";
    } else {
      local.style.display = "grid";
      foreign.style.display = "none";
      btn.textContent = "Show International Breeds";
    }
  };

  window.switchTab = function (target) {
    document.querySelectorAll(".tab-button").forEach(b => b.classList.remove("active"));
    document.querySelectorAll(".tab-content").forEach(c => c.classList.remove("active"));
    const tabBtn = document.querySelector(`[data-target="${target}"]`);
    const tabContent = document.getElementById(target);
    if (tabBtn) tabBtn.classList.add("active");
    if (tabContent) tabContent.classList.add("active");
  };

  // ====== WEATHER FORECAST ======
  async function fetchWeather(city) {
    const apiKey = "261cd8c7496e2b461a938a73832902a7";
    if (!city) return;
    const url = `https://api.openweathermap.org/data/2.5/forecast?q=${encodeURIComponent(city)}&units=metric&appid=${apiKey}`;
    const container = document.getElementById("forecast");
    if (!container) return;
    container.innerHTML = `<div class="forecast-loading">Loading...</div>`;
    try {
      const res = await fetch(url);
      if (!res.ok) throw new Error(`Weather API error: ${res.status}`);
      const data = await res.json();
      if (!data.list || data.list.length === 0) throw new Error("No forecast data");
      const uniqueDates = [];
      for (const entry of data.list) {
        const dateStr = new Date(entry.dt * 1000).toISOString().split("T")[0];
        if (!uniqueDates.includes(dateStr)) uniqueDates.push(dateStr);
        if (uniqueDates.length >= 5) break;
      }
      const daily = uniqueDates.map(dateStr => {
        const entries = data.list.filter(e =>
          new Date(e.dt * 1000).toISOString().split("T")[0] === dateStr
        );
        let pick = entries[0];
        let bestDiff = Math.abs(new Date(entries[0].dt * 1000).getHours() - 12);
        for (const e of entries) {
          const diff = Math.abs(new Date(e.dt * 1000).getHours() - 12);
          if (diff < bestDiff) { pick = e; bestDiff = diff; }
        }
        return {
          day: new Date(dateStr).toLocaleDateString("en-US", { weekday: "short" }),
          temp: Math.round(pick.main.temp),
          desc: pick.weather[0].description,
          icon: pick.weather[0].icon
        };
      });
      container.innerHTML = "";
      daily.forEach(d => {
        const card = document.createElement("div");
        card.className = "forecast-card fade-in";
        card.innerHTML = `
          <strong>${d.day}</strong>
          <div><img src="https://openweathermap.org/img/wn/${d.icon}@2x.png" alt="${d.desc}" /></div>
          <div>${d.temp}°C</div>
          <div class="desc">${d.desc}</div>
        `;
        container.appendChild(card);
      });
    } catch (err) {
      console.error(err);
      if (container) container.innerHTML = `<div class="forecast-error">Could not load weather</div>`;
    }
  }

  const citySelect = document.getElementById("city-select");
  if (citySelect) {
    citySelect.addEventListener("change", () => fetchWeather(citySelect.value));
    fetchWeather(citySelect.value || citySelect.options[0].value);
  }

  // ====== COLD ROOM BOOKING ======
  document.querySelectorAll(".cold-room-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      const name = btn.dataset.name || "this cold room";
      alert(`Slot requested at ${name}. Our team will contact you shortly.`);
    });
  });

  // ====== ADD TO CART ======
  let cartCount = 0;
  document.querySelectorAll(".add-to-cart-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      cartCount++;
      const counter = document.getElementById("cart-count");
      if (counter) counter.textContent = cartCount;
      btn.textContent = "✓ Added";
      btn.disabled = true;
      btn.style.background = "#059669";
    });
  });

  // ====== SEARCH FILTER ======
  const searchInput = document.getElementById("search-input");
  if (searchInput) {
    searchInput.addEventListener("input", () => {
      const query = searchInput.value.toLowerCase();
      document.querySelectorAll(".product-card").forEach(card => {
        const title = card.querySelector("h4");
        if (title) {
          card.style.display = title.textContent.toLowerCase().includes(query) ? "flex" : "none";
        }
      });
    });
  }

  // ====== CATEGORY FILTER ======
  const categoryFilter = document.getElementById("category-filter");
  if (categoryFilter) {
    categoryFilter.addEventListener("change", () => {
      const selected = categoryFilter.value.toLowerCase();
      document.querySelectorAll("#market-listings .product-card").forEach(card => {
        const meta = card.querySelector(".product-meta");
        if (!selected || (meta && meta.textContent.toLowerCase().includes(selected))) {
          card.style.display = "flex";
        } else {
          card.style.display = "none";
        }
      });
    });
  }

  // ====== LOAD PRODUCE FROM DB ======
  async function loadProduce() {
    try {
      const res = await fetch("/produce");
      const produce = await res.json();
      if (produce && produce.length > 0) {
        document.getElementById("market-listings").innerHTML = produce.map(p => `
          <div class="product-card">
            <div class="product-photo" style="${p.image_path ? `background-image: url('${p.image_path}')` : "background-color:#f3f4f6"}">
              ${!p.image_path ? '<div class="no-photo">No photo</div>' : ""}
            </div>
            <div class="product-body">
              <span class="verified-badge">✅ Verified</span>
              <h4>${p.title}</h4>
              <p class="product-meta">📍 ${p.location} • per ${p.unit}</p>
              <p class="product-price">₦${p.price.toLocaleString()}</p>
              <div class="product-buttons">
                <button class="add-to-cart-btn" data-item="${p.title}">Add to Cart</button>
                <button class="cold-room-btn">❄️ Cold Room</button>
              </div>
            </div>
          </div>
        `).join("");
      }
    } catch (err) {
      console.log("Using static listings");
    }
  }

  // ====== INVEST FORM ======
  const investForm = document.getElementById("invest-form");
  if (investForm) {
    investForm.addEventListener("submit", (e) => {
      e.preventDefault();
      if (!token) { window.location.href = "/login"; return; }
      alert("Investment pledge submitted! Our team will contact you shortly.");
    });
  }

  // ====== VET FORM ======
  const vetForm = document.getElementById("vet-form");
  if (vetForm) {
    vetForm.addEventListener("submit", (e) => {
      e.preventDefault();
      if (!token) { window.location.href = "/login"; return; }
      alert("Your question has been submitted. A vet will respond shortly.");
      e.target.reset();
    });
  }

  // ====== INIT ======
  updateAuthUI();
  loadProduce();

});