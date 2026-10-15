const searchInput = document.getElementById("search");
const suggestions = document.getElementById("suggestions");
const message = document.getElementById("message");
const result = document.getElementById("result");
let period = "1mo";
let timer = null;

// ---- Suggestions ----
searchInput.addEventListener("input", () => {
  clearTimeout(timer);
  const q = searchInput.value.trim();
  if (!q) return hideSuggestions();
  timer = setTimeout(() => loadSuggestions(q), 250);   // wait while typing
});

async function loadSuggestions(q) {
  try {
    const res = await fetch("/api/search?q=" + encodeURIComponent(q));
    const items = await res.json();
    suggestions.innerHTML = "";
    items.forEach(item => {
      const li = document.createElement("li");
      li.innerHTML = `<span>${item.symbol}</span><small>${item.name}</small>`;
      li.addEventListener("click", () => {
        searchInput.value = item.symbol;
        hideSuggestions();
        loadStock();
      });
      suggestions.appendChild(li);
    });
    suggestions.classList.toggle("hidden", items.length === 0);
  } catch (e) {
    hideSuggestions();
  }
}

function hideSuggestions() { suggestions.classList.add("hidden"); }
document.addEventListener("click", e => {
  if (!e.target.closest(".search-box")) hideSuggestions();
});

// ---- Buttons ----
document.getElementById("go").addEventListener("click", () => { hideSuggestions(); loadStock(); });
searchInput.addEventListener("keydown", e => {
  if (e.key === "Enter") { hideSuggestions(); loadStock(); }
});

document.querySelectorAll("#periods button").forEach(btn => {
  btn.addEventListener("click", () => {
    document.querySelectorAll("#periods button").forEach(b => b.classList.remove("active"));
    btn.classList.add("active");
    period = btn.dataset.period;
    if (searchInput.value.trim()) loadStock();
  });
});

// ---- Load stock ----
async function loadStock() {
  const ticker = searchInput.value.trim();
  if (!ticker) { message.textContent = "Please enter a stock name or symbol."; return; }

  message.style.color = "#5b6978";
  message.textContent = "Loading...";
  try {
    const res = await fetch(`/api/stock?ticker=${encodeURIComponent(ticker)}&period=${period}`);
    const d = await res.json();
    if (!res.ok) throw new Error(d.error);
    showStock(d);
    message.textContent = "";
  } catch (err) {
    message.style.color = "#c93a30";
    message.textContent = err.message || "Something went wrong.";
    result.classList.add("hidden");
  }
}

function showStock(d) {
  document.getElementById("ticker").textContent = d.ticker;
  document.getElementById("updated").textContent = "Updated: " + d.last_updated;
  document.getElementById("price").textContent = d.latest_price.toFixed(2);

  const change = document.getElementById("change");
  if (d.change !== null) {
    const sign = d.change >= 0 ? "+" : "";
    change.textContent = `${sign}${d.change.toFixed(2)} (${sign}${d.change_percent.toFixed(2)}%)`;
    change.className = d.change >= 0 ? "up" : "down";
  } else {
    change.textContent = "";
  }

  document.getElementById("high").textContent = d.high.toFixed(2);
  document.getElementById("low").textContent = d.low.toFixed(2);
  document.getElementById("volume").textContent = d.volume ? d.volume.toLocaleString() : "-";

  for (const name of ["price", "volume", "returns"]) {
    document.getElementById("chart-" + name).src = "data:image/png;base64," + d.charts[name];
  }
  result.classList.remove("hidden");
}
