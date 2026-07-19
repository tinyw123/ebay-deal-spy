// DealSpy Frontend Logic

// Global State
let trackers = [];
let deals = [];
let audioEnabled = true;
let selectedTracker = null;
let priceChart = null;

// DOM Elements
const trackerForm = document.getElementById("tracker-form");
const trackersList = document.getElementById("trackers-list");
const dealsFeed = document.getElementById("deals-feed");
const totalTrackersVal = document.getElementById("total-trackers");
const totalDealsVal = document.getElementById("total-deals");
const discountSlider = document.getElementById("tracker-discount");
const discountVal = document.getElementById("discount-val");
const toggleAudioBtn = document.getElementById("toggle-audio-btn");
const audioStatusTxt = document.getElementById("audio-status-txt");
const newDealsAlert = document.getElementById("new-deals-alert");

// Modal Elements
const detailsModal = document.getElementById("details-modal");
const closeModalBtn = document.getElementById("close-modal-btn");
const modalTitle = document.getElementById("modal-tracker-title");
const modalStatKeyword = document.getElementById("modal-stat-keyword");
const modalStatMarket = document.getElementById("modal-stat-market");
const modalStatSolds = document.getElementById("modal-stat-solds");
const modalSoldTableBody = document.getElementById("modal-sold-table-body");

// Initialize application
document.addEventListener("DOMContentLoaded", () => {
  // Setup range slider listener
  discountSlider.addEventListener("input", (e) => {
    discountVal.textContent = `${e.target.value}%`;
  });

  // Setup form submit
  trackerForm.addEventListener("submit", handleAddTracker);

  // Setup toggle sound
  toggleAudioBtn.addEventListener("click", toggleAudio);

  // Setup modal close
  closeModalBtn.addEventListener("click", hideModal);
  window.addEventListener("click", (e) => {
    if (e.target === detailsModal) hideModal();
  });

  // Initial Fetch & Start Polling
  fetchData();
  setInterval(fetchData, 5000); // Poll server every 5 seconds
});

// ----------------- Web Audio API Sound Synthesizer -----------------
function playAlertSound() {
  if (!audioEnabled) return;
  try {
    const AudioContext = window.AudioContext || window.webkitAudioContext;
    if (!AudioContext) return;
    
    const ctx = new AudioContext();
    
    // First Beep (Cyan pitch)
    const osc1 = ctx.createOscillator();
    const gain1 = ctx.createGain();
    osc1.type = "sine";
    osc1.frequency.setValueAtTime(587.33, ctx.currentTime); // D5 note
    gain1.gain.setValueAtTime(0.15, ctx.currentTime);
    gain1.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + 0.15);
    osc1.connect(gain1);
    gain1.connect(ctx.destination);
    
    // Second Beep (Emerald pitch, slightly higher and offset)
    const osc2 = ctx.createOscillator();
    const gain2 = ctx.createGain();
    osc2.type = "sine";
    osc2.frequency.setValueAtTime(880.00, ctx.currentTime + 0.08); // A5 note
    gain2.gain.setValueAtTime(0.2, ctx.currentTime + 0.08);
    gain2.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + 0.3);
    
    osc2.connect(gain2);
    gain2.connect(ctx.destination);
    
    osc1.start(ctx.currentTime);
    osc1.stop(ctx.currentTime + 0.15);
    
    osc2.start(ctx.currentTime + 0.08);
    osc2.stop(ctx.currentTime + 0.3);
  } catch (e) {
    console.error("Audio Context playback failed", e);
  }
}

function toggleAudio() {
  audioEnabled = !audioEnabled;
  if (audioEnabled) {
    audioStatusTxt.textContent = "Sound On";
    toggleAudioBtn.classList.remove("btn-secondary");
    toggleAudioBtn.classList.add("btn-primary");
    playAlertSound(); // Test beep
  } else {
    audioStatusTxt.textContent = "Sound Off";
    toggleAudioBtn.classList.remove("btn-primary");
    toggleAudioBtn.classList.add("btn-secondary");
  }
}

// ----------------- Data Fetching -----------------
async function fetchData() {
  try {
    const trackersRes = await fetch("/api/trackers");
    const newTrackers = await trackersRes.json();
    
    const dealsRes = await fetch("/api/deals");
    const newDeals = await dealsRes.json();

    // Check if new deals arrived to trigger sound alert
    if (deals.length > 0 && newDeals.length > deals.length) {
      // Find out if the new deals are actually newer than the newest we had
      const newestOldTime = Math.max(...deals.map(d => d.timestamp), 0);
      const hasNewer = newDeals.some(d => d.timestamp > newestOldTime);
      if (hasNewer) {
        playAlertSound();
        triggerNewDealsBanner();
      }
    }

    trackers = newTrackers;
    deals = newDeals;

    renderTrackers();
    renderDeals();
    
    totalTrackersVal.textContent = trackers.length;
    totalDealsVal.textContent = deals.length;
  } catch (e) {
    console.error("Error syncing with backend:", e);
    document.getElementById("scanner-status").textContent = "Offline";
    document.getElementById("scanner-status").className = "value text-muted";
  }
}

function triggerNewDealsBanner() {
  newDealsAlert.style.display = "block";
  setTimeout(() => {
    newDealsAlert.style.display = "none";
  }, 4000);
}

// ----------------- Rendering DOM Elements -----------------

function renderTrackers() {
  if (trackers.length === 0) {
    trackersList.innerHTML = `
      <div class="empty-state">
        <p>No active trackers. Add one above to start monitoring.</p>
      </div>
    `;
    return;
  }

  trackersList.innerHTML = "";
  trackers.forEach(tracker => {
    const card = document.createElement("div");
    card.className = `tracker-card ${selectedTracker && selectedTracker.id === tracker.id ? 'selected' : ''}`;
    
    const marketDisplay = tracker.market_price > 0 ? `£${tracker.market_price}` : "Calculating...";
    const badgeClass = tracker.mode === "live" ? "badge-live" : "badge-mock";
    
    card.innerHTML = `
      <div class="tracker-info">
        <span class="tracker-title">${escapeHTML(tracker.name)}</span>
        <div class="tracker-meta">
          <span class="badge ${badgeClass}">${tracker.mode}</span>
          <span>Val: <strong class="text-success">${marketDisplay}</strong></span>
        </div>
      </div>
      <div class="tracker-actions">
        <button class="btn-icon scan-btn" title="Force Manual Scan" data-id="${tracker.id}">
          <svg class="icon" viewBox="0 0 24 24"><path d="M17.65 6.35C16.2 4.9 14.21 4 12 4c-4.42 0-7.99 3.58-7.99 8s3.57 8 7.99 8c3.73 0 6.84-2.55 7.73-6h-2.08c-.82 2.33-3.04 4-5.65 4-3.31 0-6-2.69-6-6s2.69-6 6-6c1.66 0 3.14.69 4.22 1.78L13 11h7V4l-2.35 2.35z"/></svg>
        </button>
        <button class="btn-icon delete delete-btn" title="Delete Tracker" data-id="${tracker.id}">
          <svg class="icon" viewBox="0 0 24 24"><path d="M6 19c0 1.1.9 2 2 2h8c1.1 0 2-.9 2-2V7H6v12zM19 4h-3.5l-1-1h-5l-1 1H5v2h14V4z"/></svg>
        </button>
      </div>
    `;

    // Click handler to open detailed modal
    card.addEventListener("click", (e) => {
      // Don't open modal if action buttons were clicked
      if (e.target.closest(".btn-icon")) return;
      showTrackerDetails(tracker);
    });

    // Action button listeners
    card.querySelector(".scan-btn").addEventListener("click", (e) => {
      e.stopPropagation();
      handleManualScan(tracker.id, e.currentTarget);
    });

    card.querySelector(".delete-btn").addEventListener("click", (e) => {
      e.stopPropagation();
      handleDeleteTracker(tracker.id);
    });

    trackersList.appendChild(card);
  });
}

function renderDeals() {
  if (deals.length === 0) {
    dealsFeed.innerHTML = `
      <div class="deals-empty-state">
        <div class="radar-scan">
          <div class="radar-line"></div>
        </div>
        <h3>Monitoring Market Listings...</h3>
        <p>Deals matching your tracking criteria will appear here in real-time.</p>
      </div>
    `;
    return;
  }

  dealsFeed.innerHTML = "";
  deals.forEach(deal => {
    const card = document.createElement("div");
    card.className = "deal-card";
    
    const timeStr = formatTimeAgo(deal.timestamp);
    const imageHTML = deal.image 
      ? `<img src="${deal.image}" alt="Deal Image" onerror="this.src=''; this.parentNode.innerHTML='<span class=\\'deal-image-placeholder\\'>🛍️</span>'">`
      : `<span class="deal-image-placeholder">🛍️</span>`;

    card.innerHTML = `
      <div class="deal-image-container">
        ${imageHTML}
        <span class="discount-tag">${deal.discount_pct}% OFF</span>
      </div>
      <div class="deal-body">
        <div class="deal-title" title="${escapeHTML(deal.title)}">${escapeHTML(deal.title)}</div>
        
        <div class="deal-price-row">
          <div class="deal-price">
            <span class="label">Buy Cost</span>
            <span class="val">£${deal.total.toFixed(2)}</span>
          </div>
          <div class="deal-shipping">
            + £${deal.shipping.toFixed(2)} post
          </div>
          <div class="deal-market">
            <span class="label">Market Value</span>
            <span class="val">£${deal.market_price.toFixed(2)}</span>
          </div>
        </div>
        
        <div class="deal-footer">
          <span class="deal-time">${timeStr}</span>
          <a href="${deal.url}" target="_blank" class="btn btn-secondary icon-btn" style="padding: 6px 12px; font-size: 11px;">
            View Deal
            <svg viewBox="0 0 24 24" class="icon" style="width:12px; height:12px;"><path d="M19 19H5V5h7V3H5c-1.11 0-2 .9-2 2v14c0 1.1.89 2 2 2h14c1.1 0 2-.9 2-2v-7h-2v7zM14 3v2h3.59l-9.83 9.83 1.41 1.41L19 6.41V10h2V3h-7z"/></svg>
          </a>
        </div>
      </div>
    `;
    dealsFeed.appendChild(card);
  });
}

// ----------------- Actions & Handlers -----------------

async function handleAddTracker(e) {
  e.preventDefault();
  
  const name = document.getElementById("tracker-name").value;
  const keyword = document.getElementById("tracker-keyword").value;
  const discount = parseFloat(discountSlider.value);
  const mode = document.getElementById("tracker-mode").value;
  const interval = parseInt(document.getElementById("tracker-interval").value);

  const newBtn = trackerForm.querySelector('button[type="submit"]');
  newBtn.disabled = true;
  newBtn.innerHTML = `Initializing...`;

  try {
    const response = await fetch("/api/trackers", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, keyword, discount, mode, interval })
    });

    if (response.ok) {
      trackerForm.reset();
      discountSlider.value = 20;
      discountVal.textContent = "20%";
      await fetchData();
    } else {
      const err = await response.json();
      alert(`Error: ${err.error}`);
    }
  } catch (err) {
    alert("Failed to create tracker. Server offline.");
  } finally {
    newBtn.disabled = false;
    newBtn.innerHTML = `
      <svg class="icon mr-1" viewBox="0 0 24 24"><path d="M19 13h-6v6h-2v-6H5v-2h6V5h2v6h6v2z"/></svg>
      Initialize Tracker
    `;
  }
}

async function handleManualScan(id, buttonEl) {
  buttonEl.classList.add("loading");
  buttonEl.style.animation = "sweep 1s linear infinite";

  try {
    const response = await fetch(`/api/trackers/${id}/scan`, { method: "POST" });
    if (response.ok) {
      const result = await response.json();
      await fetchData();
      
      // Auto open modal detail page to view fresh statistics!
      const updatedTracker = result.tracker;
      // Load sold listings that were just parsed
      showTrackerDetails(updatedTracker, result.results.sold_listings);
    } else {
      const err = await response.json();
      alert(`Scan failed: ${err.error}`);
    }
  } catch (err) {
    alert("Connection error during scanning.");
  } finally {
    buttonEl.style.animation = "";
    buttonEl.classList.remove("loading");
  }
}

async function handleDeleteTracker(id) {
  if (!confirm("Are you sure you want to delete this tracker and all its spotted deals?")) return;
  try {
    const response = await fetch(`/api/trackers/${id}`, { method: "DELETE" });
    if (response.ok) {
      if (selectedTracker && selectedTracker.id === id) {
        hideModal();
      }
      await fetchData();
    }
  } catch (err) {
    alert("Delete failed.");
  }
}

// ----------------- Modal Details & Chart rendering -----------------

async function showTrackerDetails(tracker, preloadedSolds = null) {
  selectedTracker = tracker;
  renderTrackers(); // Refresh highlighted class

  modalTitle.textContent = `${escapeHTML(tracker.name)} Analysis`;
  modalStatKeyword.textContent = tracker.keyword;
  modalStatMarket.textContent = tracker.market_price > 0 ? `£${tracker.market_price.toFixed(2)}` : "Analyzing...";
  modalStatSolds.textContent = "Analyzing data...";
  modalSoldTableBody.innerHTML = `<tr><td colspan="4" style="text-align:center;">Loading statistical price logs...</td></tr>`;
  
  detailsModal.classList.add("show");
  
  let solds = preloadedSolds;
  
  // If we don't have preloaded listings (since scan API returns them, but standard GET doesn't persist raw solds in API)
  // We can call scan to get sold list or we will simulate/query them dynamically.
  // To keep it light, let's trigger a light scan to gather sold details if market_price is 0 or if we need fresh data.
  if (!solds) {
    try {
      modalSoldTableBody.innerHTML = `<tr><td colspan="4" style="text-align:center;">Querying database...</td></tr>`;
      const response = await fetch(`/api/trackers/${tracker.id}/scan`, { method: "POST" });
      if (response.ok) {
        const result = await response.json();
        solds = result.results.sold_listings;
        
        // Update price label since scan recalculated it
        modalStatMarket.textContent = `£${result.tracker.market_price.toFixed(2)}`;
      }
    } catch (e) {
      modalSoldTableBody.innerHTML = `<tr><td colspan="4" style="text-align:center; color: var(--accent-rose);">Failed to pull price logs from eBay.</td></tr>`;
      return;
    }
  }

  if (!solds || solds.length === 0) {
    modalStatMarket.textContent = "N/A";
    modalStatSolds.textContent = "0 listings found";
    modalSoldTableBody.innerHTML = `<tr><td colspan="4" style="text-align:center; color: var(--text-secondary);">No recent transactions found on eBay for this keyword. Try switching to Mock Mode if live queries are blocked.</td></tr>`;
    if (priceChart) {
      priceChart.destroy();
      priceChart = null;
    }
    return;
  }

  modalStatSolds.textContent = `${solds.length} listings found`;
  
  // Populate Table
  modalSoldTableBody.innerHTML = "";
  solds.forEach(item => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td title="${escapeHTML(item.title)}">${escapeHTML(item.title)}</td>
      <td class="text-right">£${item.price.toFixed(2)}</td>
      <td class="text-right">${item.shipping > 0 ? '£' + item.shipping.toFixed(2) : 'Free'}</td>
      <td class="text-right" style="font-weight: 600;">£${item.total.toFixed(2)}</td>
    `;
    modalSoldTableBody.appendChild(tr);
  });

  // Render Price Distribution Histogram
  renderChart(solds, tracker.market_price);
}

function hideModal() {
  detailsModal.classList.remove("show");
  selectedTracker = null;
  renderTrackers();
}

function renderChart(solds, marketPrice) {
  const totals = solds.map(item => item.total);
  const min = Math.min(...totals);
  const max = Math.max(...totals);
  
  // Define 10 price bins
  const binCount = 8;
  const step = (max - min) / binCount;
  const bins = Array(binCount).fill(0);
  const labels = [];
  
  for (let i = 0; i < binCount; i++) {
    const start = min + i * step;
    const end = start + step;
    labels.push(`£${Math.round(start)}-£${Math.round(end)}`);
  }

  totals.forEach(val => {
    let index = Math.floor((val - min) / step);
    if (index >= binCount) index = binCount - 1;
    if (index < 0) index = 0;
    bins[index]++;
  });

  // Highlight bin containing the market median price
  const backgroundColors = bins.map((val, idx) => {
    const start = min + idx * step;
    const end = start + step;
    if (marketPrice >= start && marketPrice <= end) {
      return "#10b981"; // Emerald for median
    }
    return "rgba(6, 182, 212, 0.4)"; // Muted cyan for normal bins
  });

  const borderColors = bins.map((val, idx) => {
    const start = min + idx * step;
    const end = start + step;
    if (marketPrice >= start && marketPrice <= end) {
      return "#10b981";
    }
    return "#06b6d4";
  });

  if (priceChart) {
    priceChart.destroy();
  }

  const ctx = document.getElementById("price-distribution-chart").getContext("2d");
  
  // Configure Chart.js
  Chart.defaults.color = "#94a3b8";
  Chart.defaults.font.family = "'Plus Jakarta Sans', sans-serif";

  priceChart = new Chart(ctx, {
    type: "bar",
    data: {
      labels: labels,
      datasets: [{
        label: "Listing Volume",
        data: bins,
        backgroundColor: backgroundColors,
        borderColor: borderColors,
        borderWidth: 1.5,
        borderRadius: 4
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false }
      },
      scales: {
        y: {
          grid: { color: "rgba(255, 255, 255, 0.04)" },
          ticks: { precision: 0 }
        },
        x: {
          grid: { display: false }
        }
      }
    }
  });
}

// ----------------- Utilities -----------------

function escapeHTML(str) {
  return str
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function formatTimeAgo(timestamp) {
  const diff = Math.floor(Date.now() / 1000) - timestamp;
  if (diff < 60) return "Just now";
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  return `${Math.floor(diff / 3600)}h ago`;
}
