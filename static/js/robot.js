const screens = {
    idle: document.getElementById("idle-screen"),
    reminder: document.getElementById("reminder-screen"),
    acknowledgement: document.getElementById("ack-screen"),
};

const developerPanel = document.getElementById("developer-panel");
const panelBackdrop = document.getElementById("panel-backdrop");
const conditionSelect = document.getElementById("condition-select");
const participantInput = document.getElementById("participant-id");
const displayNameInput = document.getElementById("display-name");
const reminderSelect = document.getElementById("reminder-select");
const triggerButton = document.getElementById("trigger-reminder");
const acknowledgeButton = document.getElementById("acknowledge-button");
const toast = document.getElementById("toast");

let publicConfig = null;
let currentReminderKey = null;
let acknowledging = false;
let toastTimer = null;

function showScreen(name) {
    Object.entries(screens).forEach(([key, element]) => {
        element.classList.toggle("active", key === name);
    });
}

function updateClock() {
    const now = new Date();
    document.getElementById("clock").textContent = now.toLocaleTimeString([], {
        hour: "2-digit",
        minute: "2-digit",
    });

    const hour = now.getHours();
    const greeting = hour < 12 ? "Good morning" : hour < 18 ? "Good afternoon" : "Good evening";
    document.getElementById("idle-greeting").textContent = greeting;
}

function showToast(message, isError = false) {
    clearTimeout(toastTimer);
    toast.textContent = message;
    toast.classList.toggle("error", isError);
    toast.classList.add("show");
    toastTimer = setTimeout(() => toast.classList.remove("show"), 2600);
}

async function api(url, options = {}) {
    const response = await fetch(url, {
        headers: { "Content-Type": "application/json", ...(options.headers || {}) },
        ...options,
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
        throw new Error(data.error || `Request failed (${response.status})`);
    }
    return data;
}

function beep() {
    try {
        const AudioContextClass = window.AudioContext || window.webkitAudioContext;
        if (!AudioContextClass) return;
        const context = new AudioContextClass();
        const oscillator = context.createOscillator();
        const gain = context.createGain();
        oscillator.frequency.value = 660;
        gain.gain.setValueAtTime(0.12, context.currentTime);
        gain.gain.exponentialRampToValueAtTime(0.001, context.currentTime + 0.45);
        oscillator.connect(gain);
        gain.connect(context.destination);
        oscillator.start();
        oscillator.stop(context.currentTime + 0.45);
        oscillator.addEventListener("ended", () => context.close());
    } catch (error) {
        console.warn("Beep unavailable:", error);
    }
}

function speak(text) {
    if (!("speechSynthesis" in window) || !text) return;
    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.rate = 0.92;
    utterance.pitch = 1.0;
    window.speechSynthesis.speak(utterance);
}

function renderReminder(active, playAudio = true) {
    if (!active) return;
    const condition = active.condition;
    const key = `${active.started_at}-${condition.name}`;
    const isNew = key !== currentReminderKey;
    currentReminderKey = key;

    document.body.classList.toggle("high-social", Boolean(condition.face_animation));
    document.getElementById("reminder-symbol").textContent = active.symbol;
    document.getElementById("condition-label").textContent = `${condition.label} · ${condition.social_cue_count} social cue(s)`;
    document.getElementById("reminder-title").textContent = active.title;
    document.getElementById("reminder-message").textContent = active.message;

    const greetingElement = document.getElementById("personal-greeting");
    if (condition.personalised_greeting) {
        greetingElement.textContent = active.display_name ? `Hello, ${active.display_name}.` : "Hello.";
    } else {
        greetingElement.textContent = "";
    }

    showScreen("reminder");

    if (playAudio && isNew) {
        if (condition.voice_reminder) {
            speak(active.voice_message);
        } else {
            beep();
        }
    }
}

function renderAcknowledgement(result, conditionName = "HIGH", playAudio = true) {
    if (!result) return;
    const seconds = (result.response_time_ms / 1000).toFixed(2);
    document.getElementById("response-time").textContent = `${seconds} s`;
    showScreen("acknowledgement");
    if (playAudio && conditionName === "HIGH") speak("Thank you.");
}

async function triggerReminder() {
    triggerButton.disabled = true;
    try {
        const data = await api("/api/reminder/start", {
            method: "POST",
            body: JSON.stringify({
                participant_id: participantInput.value.trim() || "P001",
                display_name: displayNameInput.value.trim(),
                condition: conditionSelect.value,
                reminder_type: reminderSelect.value,
            }),
        });
        closeDeveloperPanel();
        renderReminder(data.active_reminder, true);
    } catch (error) {
        showToast(error.message, true);
    } finally {
        triggerButton.disabled = false;
    }
}

async function acknowledgeReminder() {
    if (acknowledging) return;
    acknowledging = true;
    acknowledgeButton.disabled = true;
    try {
        const data = await api("/api/reminder/acknowledge", { method: "POST", body: "{}" });
        const conditionName = data.active_reminder?.condition?.name || "LOW";
        renderAcknowledgement(data.last_result, conditionName, true);
        await loadTrials();

        const delayMs = Math.max(1000, Number(document.body.dataset.ackSeconds || 2.5) * 1000);
        window.setTimeout(async () => {
            try {
                await api("/api/reminder/reset", { method: "POST", body: "{}" });
            } catch (error) {
                console.warn(error);
            }
            currentReminderKey = null;
            showScreen("idle");
        }, delayMs);
    } catch (error) {
        showToast(error.message, true);
    } finally {
        acknowledging = false;
        acknowledgeButton.disabled = false;
    }
}

function openDeveloperPanel() {
    developerPanel.classList.add("open");
    developerPanel.setAttribute("aria-hidden", "false");
    panelBackdrop.hidden = false;
    loadTrials();
}

function closeDeveloperPanel() {
    developerPanel.classList.remove("open");
    developerPanel.setAttribute("aria-hidden", "true");
    panelBackdrop.hidden = true;
}

function updateCueSummary() {
    if (!publicConfig) return;
    const condition = publicConfig.conditions[conditionSelect.value];
    document.getElementById("cue-summary").textContent =
        `${condition.name} condition: ${condition.social_cue_count} social cue(s) enabled.`;
}

async function loadTrials() {
    try {
        const data = await api("/api/trials?limit=12");
        document.getElementById("trial-count").textContent = data.count;
        const body = document.getElementById("trial-table-body");
        if (!data.trials.length) {
            body.innerHTML = '<tr><td colspan="6">No trials yet.</td></tr>';
            return;
        }
        body.innerHTML = data.trials.map((trial) => `
            <tr>
                <td>${trial.id}</td>
                <td>${escapeHtml(trial.participant_id)}</td>
                <td>${escapeHtml(trial.condition_name)}</td>
                <td>${escapeHtml(trial.reminder_type)}</td>
                <td>${trial.social_cue_count}</td>
                <td>${(trial.response_time_ms / 1000).toFixed(2)} s</td>
            </tr>
        `).join("");
    } catch (error) {
        showToast(`Could not load trials: ${error.message}`, true);
    }
}

function escapeHtml(value) {
    return String(value ?? "").replace(/[&<>'"]/g, (char) => ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        "'": "&#39;",
        '"': "&quot;",
    }[char]));
}

async function testHardware(action) {
    try {
        const data = await api("/api/hardware/test", {
            method: "POST",
            body: JSON.stringify({ action }),
        });
        showToast(data.message);
    } catch (error) {
        showToast(error.message, true);
    }
}

async function syncState() {
    try {
        const data = await api("/api/state");
        if (data.mode === "reminder" && data.active_reminder) {
            renderReminder(data.active_reminder, false);
        } else if (data.mode === "acknowledgement" && data.last_result) {
            renderAcknowledgement(data.last_result, data.active_reminder?.condition?.name || "LOW", false);
        } else if (data.mode === "idle") {
            showScreen("idle");
        }
    } catch (error) {
        console.warn("State sync failed:", error);
    }
}

async function initialise() {
    updateClock();
    setInterval(updateClock, 1000);

    try {
        publicConfig = await api("/api/config");
        participantInput.value = publicConfig.default_participant_id || "P001";
        displayNameInput.value = publicConfig.default_display_name || "";
        conditionSelect.value = publicConfig.default_condition || "HIGH";
        document.getElementById("hardware-mode").textContent = `${publicConfig.hardware_mode} hardware`;
        updateCueSummary();
        await syncState();
    } catch (error) {
        showToast(`Startup error: ${error.message}`, true);
    }
}

document.getElementById("developer-toggle").addEventListener("click", openDeveloperPanel);
document.getElementById("developer-close").addEventListener("click", closeDeveloperPanel);
panelBackdrop.addEventListener("click", closeDeveloperPanel);
triggerButton.addEventListener("click", triggerReminder);
acknowledgeButton.addEventListener("click", acknowledgeReminder);
conditionSelect.addEventListener("change", updateCueSummary);

document.querySelectorAll(".hardware-test").forEach((button) => {
    button.addEventListener("click", () => testHardware(button.dataset.action));
});

document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && developerPanel.classList.contains("open")) closeDeveloperPanel();
});

initialise();
