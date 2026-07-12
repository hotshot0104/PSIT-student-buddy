// ================================================================
// PSIT Student Buddy — Dashboard Logic
// Dynamic logic fetching from local Python backend API
// ================================================================

// ── Mock Data Fallback ──────────────────────────────────────────
const MOCK = {
  student: { name: "Sameer (Mock)", roll: "2200270130035", branch: "CSE, Sem 5" },
  attendance: {
    overall: 78.5,
    percent: "78.50%",
    present: 94,
    total: 120,
    subjects: [
      { name: "Data Structures & Algorithms", percent: 85.7, present: 18, total: 21 },
      { name: "Computer Networks",            percent: 76.2, present: 16, total: 21 },
      { name: "Operating Systems",            percent: 71.4, present: 15, total: 21 },
      { name: "Database Management System",   percent: 80.0, present: 20, total: 25 },
      { name: "Software Engineering",         percent: 75.0, present: 15, total: 20 },
      { name: "Machine Learning",             percent: 83.3, present: 10, total: 12 },
    ],
  },
  timetable: {
    Monday:    [
      { time: "09:25 AM", subject: "Data Structures" },
      { time: "10:25 AM", subject: "Computer Networks" },
      { time: "01:25 PM", subject: "Operating Systems" },
    ],
    Tuesday:   [
      { time: "09:25 AM", subject: "Database Management" },
      { time: "11:25 AM", subject: "Software Engineering" },
      { time: "02:25 PM", subject: "Machine Learning" },
    ],
    Wednesday: [
      { time: "09:25 AM", subject: "Data Structures" },
      { time: "10:25 AM", subject: "Operating Systems" },
      { time: "12:25 PM", subject: "Computer Networks" },
    ],
    Thursday:  [
      { time: "09:25 AM", subject: "Machine Learning" },
      { time: "11:25 AM", subject: "Database Management" },
    ],
    Friday:    [
      { time: "09:25 AM", subject: "Software Engineering" },
      { time: "10:25 AM", subject: "Data Structures" },
      { time: "01:25 PM", subject: "Computer Networks" },
      { time: "02:25 PM", subject: "Operating Systems" },
    ],
    Saturday:  [],
  },
  today_classes: [
    { time: "09:25 AM", subject: "Data Structures" },
    { time: "10:25 AM", subject: "Computer Networks" },
    { time: "01:25 PM", subject: "Operating Systems" }
  ],
  absentToday: ["Operating Systems"],
};

// ── Active Data Holder ──────────────────────────────────────────
let DATA = MOCK;
let isLive = false;

// ── Helpers ──────────────────────────────────────────────────────
const IST_OFFSET = 5.5 * 60 * 60 * 1000; // ms

function nowIST() {
  return new Date(Date.now() + IST_OFFSET - new Date().getTimezoneOffset() * 60000);
}

function parseClassTime(timeStr) {
  const [timePart, ampm] = timeStr.split(" ");
  let [h, m] = timePart.split(":").map(Number);
  if (ampm === "PM" && h < 12) h += 12;
  if (ampm === "AM" && h === 12) h = 0;
  const now = nowIST();
  return new Date(now.getFullYear(), now.getMonth(), now.getDate(), h, m, 0);
}

function attendanceColor(pct) {
  if (pct >= 75) return "success";
  if (pct >= 65) return "warning";
  return "danger";
}

function attendanceEmoji(pct) {
  if (pct >= 75) return "✅";
  if (pct >= 65) return "⚠️";
  return "🚨";
}

const DAY_NAMES = ["Sunday","Monday","Tuesday","Wednesday","Thursday","Friday","Saturday"];

// ── Live Clock ───────────────────────────────────────────────────
function updateClock() {
  const now = nowIST();
  const pad = n => String(n).padStart(2, "0");
  const h = now.getHours(), m = now.getMinutes(), s = now.getSeconds();
  const ampm = h >= 12 ? "PM" : "AM";
  const h12 = h % 12 || 12;
  const day = DAY_NAMES[now.getDay()];
  const date = now.toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" });
  document.querySelectorAll(".live-clock").forEach(el => {
    el.textContent = `${day}, ${date} · ${pad(h12)}:${pad(m)}:${pad(s)} ${ampm} IST`;
  });
}
setInterval(updateClock, 1000);
updateClock();

// ── Navigation ───────────────────────────────────────────────────
function showPage(id) {
  document.querySelectorAll(".page").forEach(p => p.classList.remove("active"));
  document.querySelectorAll(".nav-item").forEach(n => n.classList.remove("active"));
  
  const targetPage = document.getElementById("page-" + id);
  if (targetPage) targetPage.classList.add("active");
  
  const targetNav = document.querySelector(`[data-page="${id}"]`);
  if (targetNav) targetNav.classList.add("active");
  
  if (id === "dashboard") renderDashboard();
  if (id === "timetable") renderTimetable();
  if (id === "attendance") renderAttendance();
  if (id === "simulator") renderSimulator();
}

document.querySelectorAll(".nav-item[data-page]").forEach(btn => {
  btn.addEventListener("click", () => showPage(btn.dataset.page));
});

// ── Attendance Gauge (SVG) ────────────────────────────────────────
function buildGauge(pct) {
  const radius = 70;
  const circ   = 2 * Math.PI * radius;
  const dash   = (pct / 100) * circ;
  const color  = pct >= 75 ? "#10b981" : pct >= 65 ? "#f59e0b" : "#ef4444";

  document.getElementById("gauge-pct").textContent = pct.toFixed(1) + "%";
  document.getElementById("gauge-pct").className = "gauge-pct color-" + attendanceColor(pct);

  const fill = document.getElementById("gauge-fill");
  if (fill) {
    fill.setAttribute("stroke-dasharray", `${dash} ${circ}`);
    fill.setAttribute("stroke", color);
    fill.style.filter = `drop-shadow(0 0 8px ${color})`;
    fill.style.transition = "stroke-dasharray 1.5s cubic-bezier(0.4,0,0.2,1)";
  }
}

// ── Bunk Budget Calculator ───────────────────────────────────────
function calcBunkBudget(present, total) {
  const canBunk    = Math.max(0, Math.floor((present / 0.75) - total));
  const needAttend = present / total < 0.75
    ? Math.max(0, Math.ceil((0.75 * total - present) / 0.25))
    : 0;
  return { canBunk, needAttend };
}

// ── Today's Timeline ─────────────────────────────────────────────
function buildTimeline(classes) {
  const wrap = document.getElementById("today-timeline");
  if (!wrap) return;
  wrap.innerHTML = "";

  const now = nowIST();

  if (!classes || classes.length === 0) {
    wrap.innerHTML = `
      <div class="no-class">
        <span class="emoji">🎉</span>
        <strong>No classes today!</strong>
        <p style="margin-top:6px;font-size:13px;color:var(--text-3)">Enjoy your free day.</p>
      </div>`;
    return;
  }

  classes.forEach((cls, i) => {
    const classTime   = parseClassTime(cls.time);
    const endTime     = new Date(classTime.getTime() + 60 * 60 * 1000); // assume 1h
    const isDone      = now > endTime;
    const isNext      = !isDone && now < classTime &&
                        (i === 0 || now > parseClassTime(classes[i-1].time));
    const isActive    = now >= classTime && now <= endTime;

    let stateClass = "";
    let badge      = "";
    if (isDone)   { stateClass = "done";     badge = `<span class="timeline-badge badge-done">Done</span>`; }
    if (isNext)   { stateClass = "next";     badge = `<span class="timeline-badge badge-next">Up Next</span>`; }
    if (isActive) { stateClass = "next";     badge = `<span class="timeline-badge badge-next">In Progress</span>`; }

    const item = document.createElement("div");
    item.className = `timeline-item ${stateClass}`;
    item.style.animationDelay = `${i * 0.1}s`;
    item.innerHTML = `
      <div class="timeline-time">${cls.time}</div>
      <div class="timeline-subject">${cls.subject}${badge}</div>
    `;
    wrap.appendChild(item);
  });
}

// ── Dashboard Render ─────────────────────────────────────────────
function renderDashboard() {
  const { attendance, absentToday, today_classes } = DATA;

  // Greeting
  const h = nowIST().getHours();
  const greeting = h < 12 ? "Good morning" : h < 17 ? "Good afternoon" : "Good evening";
  document.getElementById("greeting").textContent = `${greeting}, ${DATA.student.name}! 👋`;
  document.getElementById("student-info").textContent =
    `${DATA.student.roll} · ${DATA.student.branch} ${isLive ? '🟢 Live' : '🟠 Mock Data'}`;

  // Absent banner
  const banner = document.getElementById("absent-banner");
  if (absentToday && absentToday.length > 0) {
    banner.classList.remove("hidden");
    document.getElementById("absent-subjects").textContent =
      `Absent in: ${absentToday.join(", ")}`;
  } else {
    banner.classList.add("hidden");
  }

  // Gauge
  buildGauge(attendance.overall);
  document.getElementById("gauge-present").textContent = attendance.present;
  document.getElementById("gauge-total").textContent   = attendance.total;

  // Bunk Budget
  const budget = calcBunkBudget(attendance.present, attendance.total);
  const bunkEl = document.getElementById("bunk-count");
  if (budget.canBunk > 0) {
    bunkEl.textContent = budget.canBunk;
    bunkEl.className   = "bunk-big color-success";
    document.getElementById("bunk-label").textContent = "classes you can still skip";
    document.getElementById("bunk-recover").style.display = "none";
  } else {
    bunkEl.textContent = budget.needAttend;
    bunkEl.className   = "bunk-big color-danger";
    document.getElementById("bunk-label").textContent = "classes needed to reach 75%";
    const recoverEl = document.getElementById("bunk-recover");
    recoverEl.style.display = "block";
    recoverEl.textContent   = `🚨 Attend ${budget.needAttend} consecutive classes to recover.`;
  }

  // Timeline
  buildTimeline(today_classes);
}

// ── Timetable Render ─────────────────────────────────────────────
function renderTimetable() {
  const grid = document.getElementById("week-grid");
  if (!grid) return;
  grid.innerHTML = "";

  const todayName = DAY_NAMES[nowIST().getDay()];
  const days = ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday"];

  days.forEach(day => {
    const classes    = DATA.timetable[day] || [];
    const isToday    = day === todayName;
    const col        = document.createElement("div");
    col.className    = `day-col${isToday ? " today" : ""}`;

    col.innerHTML = `<div class="day-header">${day.slice(0,3)}</div>`;

    if (classes.length === 0) {
      col.innerHTML += `<div class="no-class-pill">—</div>`;
    } else {
      classes.forEach(cls => {
        const pill = document.createElement("div");
        pill.className = "class-pill";
        pill.innerHTML = `<div class="pill-time">${cls.time}</div>${cls.subject}`;
        col.appendChild(pill);
      });
    }
    grid.appendChild(col);
  });
}

// ── Attendance Detail Render ──────────────────────────────────────
function renderAttendance() {
  const grid = document.getElementById("attendance-grid");
  if (!grid) return;
  grid.innerHTML = "";

  document.getElementById("att-overall-pct").textContent = DATA.attendance.percent;

  DATA.attendance.subjects.forEach(s => {
    const pct   = s.percent;
    const color = attendanceColor(pct);
    const emoji = attendanceEmoji(pct);
    const card  = document.createElement("div");
    card.className = "subject-card";
    card.innerHTML = `
      <div class="subject-name" title="${s.name}">${s.name}</div>
      <div class="subject-meta">
        <span>${s.present} / ${s.total} classes</span>
        <span class="subject-pct color-${color}">${emoji} ${pct.toFixed(1)}%</span>
      </div>
      <div class="progress-track">
        <div class="progress-fill fill-${color}" style="width: 0%"
             data-target="${pct}"></div>
      </div>
    `;
    grid.appendChild(card);
  });

  requestAnimationFrame(() => {
    document.querySelectorAll(".progress-fill[data-target]").forEach(el => {
      el.style.width = el.dataset.target + "%";
    });
  });
}

// ── Settings Save ─────────────────────────────────────────────────
document.getElementById("settings-form").addEventListener("submit", async function(e) {
  e.preventDefault();
  const btn = document.getElementById("save-btn");
  btn.textContent = "⏳ Saving...";
  btn.disabled = true;

  const erpUser   = document.getElementById("inp-erp-user").value.trim();
  const erpPass   = document.getElementById("inp-erp-pass").value.trim();
  const tgId      = document.getElementById("inp-tg-id").value.trim();
  const tgToken   = document.getElementById("inp-tg-token").value.trim();
  const remindMin = document.getElementById("inp-remind").value.trim();

  // Save to localStorage
  if (erpUser)   localStorage.setItem("erp_user",    erpUser);
  if (erpPass)   localStorage.setItem("erp_pass",    erpPass);
  if (tgId)      localStorage.setItem("telegram_id", tgId);
  if (tgToken)   localStorage.setItem("telegram_token", tgToken);
  if (remindMin) localStorage.setItem("remind_min",  remindMin);

  try {
    const response = await fetch("http://127.0.0.1:5000/api/settings", {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        erp_user: erpUser,
        erp_pass: erpPass,
        telegram_id: tgId,
        telegram_token: tgToken
      })
    });

    if (response.ok) {
      btn.textContent = "✅ Saved & Applied!";
      // Reload page data to reflect the new credentials immediately
      setTimeout(() => {
        fetchLiveData();
      }, 1000);
    } else {
      btn.textContent = "❌ Server Error";
    }
  } catch (err) {
    console.error("Failed to connect to local server settings API:", err);
    btn.textContent = "✅ Saved Locally Only";
  } finally {
    btn.disabled = false;
    setTimeout(() => { btn.textContent = "Save Settings"; }, 3000);
  }
});

// Restore saved settings on load
["erp_user", "erp_pass", "telegram_id", "telegram_token", "remind_min"].forEach(key => {
  const val = localStorage.getItem(key);
  const el  = document.getElementById("inp-" + key.replace("_","-"));
  if (val && el) el.value = val;
});

// ── Fetch Live Data from Backend ──────────────────────────────────
async function fetchLiveData() {
  const statusEl = document.querySelector(".bot-status");
  try {
    // Attempt to hit the local Python API endpoint
    const response = await fetch("http://127.0.0.1:5000/api/data");
    if (!response.ok) throw new Error("API response error");
    
    const liveData = await response.json();
    DATA = liveData;
    isLive = true;
    
    if (statusEl) {
      statusEl.innerHTML = '<div class="status-dot"></div> Live ERP Connected';
      statusEl.querySelector('.status-dot').style.background = 'var(--success)';
    }
  } catch (err) {
    console.warn("⚠️ Local backend server is not running. Displaying Mock Data instead.", err);
    DATA = MOCK;
    isLive = false;
    
    if (statusEl) {
      statusEl.innerHTML = '<div class="status-dot" style="background: var(--warning); box-shadow: 0 0 8px var(--warning)"></div> Mock Mode (Server Offline)';
    }
  } finally {
    // Boot the dashboard view
    showPage("dashboard");
  }
}

// ── Boot ──────────────────────────────────────────────────────────
fetchLiveData();

// ── Bunk Simulator Logic ──────────────────────────────────────────
let simState = {}; // Holds dynamic simulated edits per subject index

function renderSimulator() {
  const grid = document.getElementById("simulator-grid");
  if (!grid) return;
  grid.innerHTML = "";

  const subjects = DATA.attendance.subjects;
  
  // Initialize simulation state if empty or changed
  subjects.forEach((s, idx) => {
    if (simState[idx] === undefined) {
      simState[idx] = { attend: 0, bunk: 0 };
    }
  });

  function recalculateAll() {
    let totalPresent = 0;
    let totalClasses = 0;

    subjects.forEach((s, idx) => {
      const state = simState[idx];
      const p = s.present + state.attend;
      const t = s.total + state.attend + state.bunk;
      totalPresent += p;
      totalClasses += t;

      // Update subject card locally
      const card = document.getElementById(`sim-card-${idx}`);
      if (card) {
        const pct = t > 0 ? (p / t) * 100 : 0.0;
        const color = attendanceColor(pct);
        const emoji = attendanceEmoji(pct);
        
        card.querySelector(".subject-pct").className = `subject-pct color-${color}`;
        card.querySelector(".subject-pct").innerHTML = `${emoji} ${pct.toFixed(2)}%`;
        card.querySelector(".subject-meta span").textContent = `${p} / ${t} classes`;
        
        const bar = card.querySelector(".progress-fill");
        bar.className = `progress-fill fill-${color}`;
        bar.style.width = `${pct}%`;

        // Update value badges
        card.querySelector(`.sim-badge-attend`).textContent = state.attend;
        card.querySelector(`.sim-badge-bunk`).textContent = state.bunk;

        // Update bunk budget descriptor text
        const budget = calcBunkBudget(p, t);
        const metaText = card.querySelector(".sim-meta-text");
        if (budget) {
          if (budget.canBunk > 0) {
            metaText.innerHTML = `✅ You can skip <strong>${budget.canBunk}</strong> more class(es).`;
            metaText.className = "sim-meta-text color-success";
          } else {
            metaText.innerHTML = `🚨 Attend <strong>${budget.needAttend}</strong> consecutive class(es) to recover.`;
            metaText.className = "sim-meta-text color-danger";
          }
        }
      }
    });

    // Update overall simulated summary
    const overallPct = totalClasses > 0 ? (totalPresent / totalClasses) * 100 : 0.0;
    document.getElementById("sim-overall-pct").textContent = `${overallPct.toFixed(2)}%`;
    
    const pctColor = attendanceColor(overallPct);
    document.getElementById("sim-overall-pct").className = `color-${pctColor}`;
    
    const statusEl = document.getElementById("sim-overall-status");
    const verdictEl = document.getElementById("sim-overall-verdict");

    if (overallPct >= 75) {
      statusEl.textContent = "Safe Zone";
      statusEl.className = "color-success";
      verdictEl.textContent = "Your simulated average stays above 75%. Keep it up!";
    } else if (overallPct >= 65) {
      statusEl.textContent = "Caution Zone";
      statusEl.className = "color-warning";
      verdictEl.textContent = "Close to the line! Attend classes regularly to avoid alerts.";
    } else {
      statusEl.textContent = "Critical Danger";
      statusEl.className = "color-danger";
      verdictEl.textContent = "Under 75%! You will receive automated warnings and cannot bunk any more.";
    }
  }

  // Build the Simulation Cards
  subjects.forEach((s, idx) => {
    const card = document.createElement("div");
    card.className = "subject-card";
    card.id = `sim-card-${idx}`;
    
    const pct = s.percent;
    const color = attendanceColor(pct);
    const emoji = attendanceEmoji(pct);
    const state = simState[idx];

    card.innerHTML = `
      <div class="subject-name" title="${s.name}">${s.name}</div>
      <div class="subject-meta">
        <span>${s.present} / ${s.total} classes</span>
        <span class="subject-pct color-${color}">${emoji} ${pct.toFixed(2)}%</span>
      </div>
      <div class="progress-track" style="margin-bottom:16px;">
        <div class="progress-fill fill-${color}" style="width: ${pct}%"></div>
      </div>
      
      <!-- Simulation Controls -->
      <div class="sim-controls">
        <div class="sim-row">
          <span class="sim-slider-label">Attend future classes:</span>
          <div class="sim-slider-wrap">
            <input type="range" class="sim-slider sim-input-attend" 
              min="0" max="30" value="${state.attend}" data-idx="${idx}" />
            <span class="sim-value-badge sim-badge-attend">${state.attend}</span>
          </div>
        </div>
        <div class="sim-row">
          <span class="sim-slider-label">Bunk future classes:</span>
          <div class="sim-slider-wrap">
            <input type="range" class="sim-slider sim-input-bunk" 
              min="0" max="20" value="${state.bunk}" data-idx="${idx}" />
            <span class="sim-value-badge sim-badge-bunk">${state.bunk}</span>
          </div>
        </div>
      </div>
      <div class="sim-meta-text">Drag sliders to simulate budget...</div>
    `;

    // Sliders event listeners
    card.querySelector(".sim-input-attend").addEventListener("input", function(e) {
      simState[idx].attend = parseInt(e.target.value) || 0;
      recalculateAll();
    });

    card.querySelector(".sim-input-bunk").addEventListener("input", function(e) {
      simState[idx].bunk = parseInt(e.target.value) || 0;
      recalculateAll();
    });

    grid.appendChild(card);
  });

  // Perform initial calculation run
  recalculateAll();
}

