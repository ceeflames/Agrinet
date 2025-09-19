document.addEventListener("DOMContentLoaded", () => {
  // ====== Tabs ======
  const tabButtons = document.querySelectorAll(".tab-button");
  const tabContents = document.querySelectorAll(".tab-content");

  tabButtons.forEach(btn => {
    btn.addEventListener("click", () => {
      const target = btn.dataset.target;

      tabButtons.forEach(b => b.classList.remove("active"));
      btn.classList.add("active");

      tabContents.forEach(tc => {
        if (tc.id === target) {
          tc.classList.add("active");
          tc.classList.add("fade-in");
        } else {
          tc.classList.remove("active");
          tc.classList.remove("fade-in");
        }
      });
    });
  });

 // ==================== WEATHER FORECAST WITH ICONS ====================

async function fetchWeather(city) {
  const apiKey = "261cd8c7496e2b461a938a73832902a7"; // <-- replace with your real API key
  if (!city) return;

  const url = `https://api.openweathermap.org/data/2.5/forecast?q=${encodeURIComponent(city)}&units=metric&appid=${apiKey}`;
  const container = document.getElementById("forecast");
  container.innerHTML = `<div class="forecast-loading">Loading...</div>`;

  try {
    const res = await fetch(url);
    if (!res.ok) throw new Error(`Weather API error: ${res.status}`);
    const data = await res.json();
    if (!data.list || data.list.length === 0) throw new Error("No forecast data");

    // Collect unique dates (up to 5 days)
    const uniqueDates = [];
    for (const entry of data.list) {
      const dateStr = new Date(entry.dt * 1000).toISOString().split("T")[0];
      if (!uniqueDates.includes(dateStr)) uniqueDates.push(dateStr);
      if (uniqueDates.length >= 5) break;
    }

    // Pick forecast closest to midday for each date
    const daily = uniqueDates.map(dateStr => {
      const entries = data.list.filter(e =>
        new Date(e.dt * 1000).toISOString().split("T")[0] === dateStr
      );
      let pick = entries[0];
      let bestDiff = Math.abs(new Date(entries[0].dt * 1000).getHours() - 12);
      for (const e of entries) {
        const diff = Math.abs(new Date(e.dt * 1000).getHours() - 12);
        if (diff < bestDiff) {
          pick = e;
          bestDiff = diff;
        }
      }
      const dayName = new Date(dateStr).toLocaleDateString("en-US", { weekday: "short" });
      return {
        date: dateStr,
        day: dayName,
        temp: Math.round(pick.main.temp),
        desc: pick.weather[0].description,
        icon: pick.weather[0].icon // OpenWeatherMap icon code
      };
    });

    // Render forecast cards
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
    container.innerHTML = `<div class="forecast-error">Could not load weather</div>`;
  }
}

// Auto-fetch when city changes
const citySelect = document.getElementById("city-select");
if (citySelect) {
  citySelect.addEventListener("change", () => fetchWeather(citySelect.value));
  fetchWeather(citySelect.value || citySelect.options[0].value);
}



  // ====== International Toggle ======
  const intlToggle = document.getElementById("intl-toggle");
  if (intlToggle) {
    intlToggle.addEventListener("click", () => {
      const foreignSection = document.getElementById("foreign-breeds");
      const localSection = document.getElementById("local-feeds");

      const isOn = intlToggle.dataset.state === "on";
      if (isOn) {
        intlToggle.dataset.state = "off";
        intlToggle.textContent = "Off";
        foreignSection.style.display = "none";
        localSection.style.display = "grid";
      } else {
        intlToggle.dataset.state = "on";
        intlToggle.textContent = "On";
        foreignSection.style.display = "grid";
        localSection.style.display = "none";
      }
    });
  }
  
  // ====== Cold Room Booking ======
  const coldButtons = document.querySelectorAll(".cold-room-btn");
  coldButtons.forEach(btn => {
    btn.addEventListener("click", () => {
      const name = btn.dataset.name;
      alert(`Requested slot at ${name}`);
    });
  });

  // ====== Add to Cart ======
  const addToCartBtns = document.querySelectorAll(".add-to-cart-btn");
  const cartCounter = document.getElementById("cart-count");
  let cartCount = 0;

  addToCartBtns.forEach(btn => {
    btn.addEventListener("click", () => {
      cartCount++;
      if (cartCounter) cartCounter.textContent = cartCount;
      const item = btn.dataset.item;
      console.log(`Added to cart: ${item}`);
      btn.textContent = "Added";
      btn.disabled = true;
    });
  });


  // ====== Search Filter ======
  const searchInput = document.getElementById("search-input");
  if (searchInput) {
    searchInput.addEventListener("input", () => {
      const query = searchInput.value.toLowerCase();
      const listings = document.querySelectorAll(".market-item");
      listings.forEach(item => {
        const title = item.dataset.title.toLowerCase();
        if (title.includes(query)) {
          item.style.display = "block";
        } else {
          item.style.display = "none";
        }
      });
    });
  }
});
