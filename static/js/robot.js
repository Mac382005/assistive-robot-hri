const screens = {
    idle: document.getElementById("idle-screen"),
    reminder: document.getElementById("reminder-screen"),
    acknowledgement: document.getElementById("ack-screen"),
};

const developerPanel = document.getElementById("developer-panel");
const panelBackdrop = document.getElementById("panel-backdrop");
const toast = document.getElementById("toast");
const idleFace = document.getElementById("robot-face");
const reminderFace = document.getElementById("reminder-face");
const ackFace = document.getElementById("ack-face");

const participantInput = document.getElementById("participant-id");
const displayNameInput = document.getElementById("display-name");
const profileConditionSelect = document.getElementById("profile-condition-select");
const conditionSelect = document.getElementById("condition-select");
const reminderSelect = document.getElementById("reminder-select");
const triggerButton = document.getElementById("trigger-reminder");
const acknowledgeButton = document.getElementById("acknowledge-button");
const snoozeButton = document.getElementById("snooze-button");

let publicConfig = null;
let currentReminderKey = null;
let currentSchedules = [];
let acknowledging = false;
let toastTimer = null;
let idleAnimationTimer = null;
let reminderFollowupTimer = null;
let reminderFollowupBusy = false;
let talkingEyeTimer = null;


/* === FEMALE_VOICE_PATCH_START === */

/*
    Pick a friendly female English voice explicitly.

    Different Windows laptops may otherwise select different
    default Web Speech voices.
*/

let preferredSpeechVoice = null;

const preferredFemaleVoiceNames = [
    "Microsoft Aria Online (Natural)",
    "Microsoft Jenny Online (Natural)",
    "Microsoft Sonia Online (Natural)",
    "Microsoft Ava Online (Natural)",
    "Microsoft Aria",
    "Microsoft Jenny",
    "Microsoft Sonia",
    "Microsoft Ava",
    "Microsoft Natasha",
    "Microsoft Zira",
    "Samantha",
    "Karen",
    "Moira",
    "Tessa",
    "Google UK English Female"
];


function refreshPreferredSpeechVoice() {

    if (!("speechSynthesis" in window)) {
        return;
    }

    const voices =
        window.speechSynthesis.getVoices();

    if (!voices.length) {
        return;
    }

    preferredSpeechVoice = null;

    // V4.1: the Control Centre can save an exact browser/system voice.
    // No voice files are bundled with the project.
    try {
        const savedVoiceName = window.localStorage.getItem("hri_robot_voice_name");
        if (savedVoiceName) {
            const savedVoice = voices.find((voice) => voice.name === savedVoiceName);
            if (savedVoice) {
                preferredSpeechVoice = savedVoice;
                console.log("HRI saved voice selected:", savedVoice.name, savedVoice.lang);
                return;
            }
        }
    } catch (error) {
        console.debug("Saved TTS voice preference unavailable:", error);
    }


    for (
        const preferredName
        of preferredFemaleVoiceNames
    ) {

        const match = voices.find(
            (voice) =>
                voice.name
                    .toLowerCase()
                    .includes(
                        preferredName.toLowerCase()
                    )
        );

        if (match) {

            preferredSpeechVoice = match;

            console.log(
                "HRI voice selected:",
                match.name,
                match.lang
            );

            return;
        }
    }


    /*
        Prefer Australian English if none of our
        explicitly female voices are installed.
    */

    preferredSpeechVoice =
        voices.find(
            (voice) =>
                /^en-AU/i.test(voice.lang)
        )
        ||
        voices.find(
            (voice) =>
                /^en/i.test(voice.lang)
        )
        ||
        voices[0];


    if (preferredSpeechVoice) {

        console.log(
            "HRI fallback voice selected:",
            preferredSpeechVoice.name,
            preferredSpeechVoice.lang
        );
    }
}


if ("speechSynthesis" in window) {

    refreshPreferredSpeechVoice();

    window.speechSynthesis.addEventListener(
        "voiceschanged",
        refreshPreferredSpeechVoice
    );
}

/* === FEMALE_VOICE_PATCH_END === */


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
    document.getElementById("today-date").textContent = now.toLocaleDateString([], {
        weekday: "short",
        day: "numeric",
        month: "short",
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
    toastTimer = setTimeout(() => toast.classList.remove("show"), 2800);
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

function escapeHtml(value) {
    return String(value ?? "").replace(/[&<>'"]/g, (char) => ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        "'": "&#39;",
        '"': "&quot;",
    }[char]));
}

function setFaceExpression(face, expression = "happy") {
    if (!face) return;
    [...face.classList]
        .filter((name) => name.startsWith("expression-"))
        .forEach((name) => face.classList.remove(name));
    face.classList.add(`expression-${expression}`);
}

// === COMPACT_SCREEN_JS_PATCH_START ===

function startTalkingEyes(face) {
    if (!face) return;

    if (talkingEyeTimer) {
        clearInterval(talkingEyeTimer);
        talkingEyeTimer = null;
    }

    face.classList.remove("talk-eyes-closed");

    let eyesClosed = false;

    talkingEyeTimer = window.setInterval(() => {
        eyesClosed = !eyesClosed;

        face.classList.toggle(
            "talk-eyes-closed",
            eyesClosed
        );
    }, 620);
}


function stopTalkingEyes(face) {
    if (talkingEyeTimer) {
        clearInterval(talkingEyeTimer);
        talkingEyeTimer = null;
    }

    face?.classList.remove("talk-eyes-closed");
}

// === COMPACT_SCREEN_JS_PATCH_END ===


function popEmoji(emoji = "✨") {
    const element = document.getElementById("emoji-pop");
    element.textContent = emoji;
    element.classList.remove("show");
    void element.offsetWidth;
    element.classList.add("show");
}

function setIdleSpeech(text) {
    document.getElementById("robot-speech").textContent = text;
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

function speak(text, face = idleFace, expression = null) {
    if (!text) return;

    /*
        Speech remains browser-based for V2.
        V3 can replace this with voice recognition / improved TTS.

        While speech is active:
            open cute eyes
                 ↓
            close curved eyes
                 ↓
            open again

        This gives the robot a more expressive conversational face.
    */

    if (!("speechSynthesis" in window)) {
        if (face) {
            if (expression) {
                setFaceExpression(face, expression);
            }

            face.classList.add("talking");
            startTalkingEyes(face);
        }

        window.setTimeout(() => {
            stopTalkingEyes(face);
            face?.classList.remove("talking");

            if (face === idleFace) {
                setFaceExpression(idleFace, "happy");
            }
        }, 1500);

        return;
    }

    window.speechSynthesis.cancel();

    const utterance = new SpeechSynthesisUtterance(text);

    refreshPreferredSpeechVoice();

    if (preferredSpeechVoice) {
        utterance.voice = preferredSpeechVoice;
        utterance.lang =
            preferredSpeechVoice.lang || "en-AU";
    } else {
        utterance.lang = "en-AU";
    }

    utterance.rate = 0.94;
    utterance.pitch = 1.05;
    utterance.volume = 1.0;

    utterance.onstart = () => {
        if (expression) {
            setFaceExpression(face, expression);
        }

        face?.classList.add("talking");

        startTalkingEyes(face);
    };

    utterance.onend = () => {
        stopTalkingEyes(face);

        face?.classList.remove("talking");

        if (face === idleFace) {
            window.setTimeout(() => {
                setFaceExpression(idleFace, "happy");
            }, 350);
        }
    };

    utterance.onerror = () => {
        stopTalkingEyes(face);

        face?.classList.remove("talking");

        if (face === idleFace) {
            setFaceExpression(idleFace, "happy");
        }
    };

    window.speechSynthesis.speak(utterance);
}

function startIdleAnimations() {
    clearInterval(idleAnimationTimer);
    idleAnimationTimer = setInterval(() => {
        if (!screens.idle.classList.contains("active") || developerPanel.classList.contains("open")) return;
        const animations = [
            () => {
                idleFace.classList.add("wink");
                popEmoji("✨");
                setTimeout(() => idleFace.classList.remove("wink"), 900);
            },
            () => {
                setFaceExpression(idleFace, "excited");
                popEmoji("💛");
                setTimeout(() => setFaceExpression(idleFace, "happy"), 1200);
            },
            () => {
                idleFace.classList.add("look-around");
                setTimeout(() => idleFace.classList.remove("look-around"), 1600);
            },
        ];
        animations[Math.floor(Math.random() * animations.length)]();
    }, 9000);
}

async function companionInteraction(intent) {
    try {
        const data = await api("/api/companion/respond", {
            method: "POST",
            body: JSON.stringify({ intent }),
        });
        setIdleSpeech(data.text);
        setFaceExpression(idleFace, data.expression || "happy");
        popEmoji(data.emoji || "✨");
        speak(data.text, idleFace, data.expression || "happy");
    } catch (error) {
        showToast(error.message, true);
    }
}


function clearReminderFollowupTimer() {
    if (reminderFollowupTimer) {
        window.clearTimeout(reminderFollowupTimer);
        reminderFollowupTimer = null;
    }
}

function reminderFollowupSeconds() {
    const value = Number(publicConfig?.reminder_followup_seconds ?? 20);
    return Math.max(8, Number.isFinite(value) ? value : 20);
}

function reminderMaxFollowups() {
    const value = Number(publicConfig?.reminder_max_followups ?? 3);
    return Math.max(0, Number.isFinite(value) ? value : 3);
}

function scheduleReminderFollowup(active) {
    clearReminderFollowupTimer();
    if (!active || !active.started_at) return;

    const completed = Number(active.followup_count || 0);
    const maximum = reminderMaxFollowups();
    if (maximum <= 0 || completed >= maximum) return;

    const expectedStartedAt = active.started_at;
    reminderFollowupTimer = window.setTimeout(() => {
        reminderFollowupTimer = null;
        requestReminderFollowup(expectedStartedAt);
    }, reminderFollowupSeconds() * 1000);
}

async function requestReminderFollowup(expectedStartedAt) {
    if (reminderFollowupBusy) return;
    if (!screens.reminder.classList.contains("active")) return;

    reminderFollowupBusy = true;
    try {
        const data = await api("/api/reminder/followup", {
            method: "POST",
            body: "{}",
        });

        if (!screens.reminder.classList.contains("active")) return;
        if (data.reminder_started_at && data.reminder_started_at !== expectedStartedAt) return;
        if (data.done) return;

        const text = String(data.text || "").trim();
        if (text) {
            document.getElementById("reminder-speech").textContent = text;
        }

        const expression = data.expression || (Number(data.attempt) >= 2 ? "caring" : "attentive");
        setFaceExpression(reminderFace, expression);

        // HIGH condition: adaptive spoken re-prompt.
        // LOW condition: preserve the original beep/text experimental cue.
        if (data.voice_enabled && text) {
            speak(text, reminderFace, expression);
        } else {
            beep();
        }

        if (Number(data.attempt || 0) < Number(data.max_followups || 0)) {
            scheduleReminderFollowup({
                started_at: expectedStartedAt,
                followup_count: Number(data.attempt || 0),
            });
        }
    } catch (error) {
        // A local server/network hiccup should not crash the reminder screen.
        // If the reminder is still active, give it another chance later.
        console.warn("Reminder follow-up unavailable:", error);
        if (screens.reminder.classList.contains("active")) {
            reminderFollowupTimer = window.setTimeout(() => {
                reminderFollowupTimer = null;
                requestReminderFollowup(expectedStartedAt);
            }, reminderFollowupSeconds() * 1000);
        }
    } finally {
        reminderFollowupBusy = false;
    }
}

function renderReminder(active, playAudio = true) {
    if (!active) return;
    const condition = active.condition;
    const key = `${active.started_at}-${condition.name}-${active.schedule_id ?? "manual"}`;
    const isNew = key !== currentReminderKey;
    currentReminderKey = key;

    document.body.classList.toggle("high-social", Boolean(condition.face_animation));
    document.getElementById("reminder-symbol").textContent = active.symbol;
    document.getElementById("condition-label").textContent = condition.name === "HIGH" ? "Friendly reminder" : "Routine reminder";
    document.getElementById("reminder-title").textContent = active.title;
    document.getElementById("reminder-message").textContent = active.message;
    document.getElementById("reminder-speech").textContent = active.voice_message || active.message;
    setFaceExpression(reminderFace, active.expression || "caring");

    const greetingElement = document.getElementById("personal-greeting");
    if (condition.personalised_greeting) {
        greetingElement.textContent = active.display_name ? `Hello, ${active.display_name}.` : "Hello.";
    } else {
        greetingElement.textContent = "";
    }

    showScreen("reminder");

    if (playAudio && isNew) {
        if (condition.voice_reminder) {
            speak(active.voice_message, reminderFace, active.expression || "caring");
        } else {
            beep();
        }
    }

    if (isNew) {
        scheduleReminderFollowup(active);
    }
}

function renderAcknowledgement(result, conditionName = "HIGH", playAudio = true) {
    if (!result) return;
    const seconds = (result.response_time_ms / 1000).toFixed(2);
    document.getElementById("response-time").textContent = `${seconds} s`;

    const snoozed = result.action === "snoozed";
    document.getElementById("ack-icon").textContent = snoozed ? "⏰" : "✓";
    document.getElementById("ack-title").textContent = snoozed ? "No problem" : "Great, all done!";
    document.getElementById("ack-message").textContent = snoozed
        ? `I will remind you again in ${result.snooze_minutes || 10} minutes.`
        : "I have marked that reminder as completed.";
    setFaceExpression(ackFace, snoozed ? "caring" : "excited");
    showScreen("acknowledgement");

    if (playAudio && conditionName === "HIGH") {
        const text = snoozed
            ? `No problem. I will remind you again in ${result.snooze_minutes || 10} minutes.`
            : "Great, thank you. I have marked that as done.";
        speak(text, ackFace, snoozed ? "caring" : "excited");
    }
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
    clearReminderFollowupTimer();
    if (acknowledging) return;
    acknowledging = true;
    acknowledgeButton.disabled = true;
    snoozeButton.disabled = true;
    try {
        const conditionName = document.body.classList.contains("high-social") ? "HIGH" : "LOW";
        const data = await api("/api/reminder/acknowledge", { method: "POST", body: "{}" });
        renderAcknowledgement(data.last_result, conditionName, true);
        await Promise.all([loadTrials(), loadToday()]);
        scheduleReturnToIdle();
    } catch (error) {
        showToast(error.message, true);
    } finally {
        acknowledging = false;
        acknowledgeButton.disabled = false;
        snoozeButton.disabled = false;
    }
}

async function snoozeReminder() {
    clearReminderFollowupTimer();
    if (acknowledging) return;
    acknowledging = true;
    acknowledgeButton.disabled = true;
    snoozeButton.disabled = true;
    const minutes = Number(document.body.dataset.snoozeMinutes || 10);
    try {
        const conditionName = document.body.classList.contains("high-social") ? "HIGH" : "LOW";
        const data = await api("/api/reminder/snooze", {
            method: "POST",
            body: JSON.stringify({ minutes }),
        });
        renderAcknowledgement(data.last_result, conditionName, true);
        await loadTrials();
        scheduleReturnToIdle();
    } catch (error) {
        showToast(error.message, true);
    } finally {
        acknowledging = false;
        acknowledgeButton.disabled = false;
        snoozeButton.disabled = false;
    }
}

function scheduleReturnToIdle() {
    clearReminderFollowupTimer();
    const delayMs = Math.max(1200, Number(document.body.dataset.ackSeconds || 3) * 1000);
    window.setTimeout(async () => {
        try {
            await api("/api/reminder/reset", { method: "POST", body: "{}" });
        } catch (error) {
            console.warn(error);
        }
        currentReminderKey = null;
        document.body.classList.remove("high-social");
        showScreen("idle");
        setFaceExpression(idleFace, "happy");
        setIdleSpeech("I am ready when you need me.");
    }, delayMs);
}

function openDeveloperPanel() {
    developerPanel.classList.add("open");
    developerPanel.setAttribute("aria-hidden", "false");
    panelBackdrop.hidden = false;
    Promise.all([loadProfile(), loadSchedules(), loadTrials()]);
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
        `${condition.name}: ${condition.social_cue_count} social cue(s) enabled for experiment testing.`;
}

async function loadProfile() {
    try {
        const data = await api("/api/profile");
        participantInput.value = data.participant_id || "P001";
        displayNameInput.value = data.display_name || "";
        profileConditionSelect.value = data.default_condition || "HIGH";
    } catch (error) {
        showToast(`Could not load profile: ${error.message}`, true);
    }
}

async function saveProfile() {
    try {
        const data = await api("/api/profile", {
            method: "PUT",
            body: JSON.stringify({
                participant_id: participantInput.value.trim() || "P001",
                display_name: displayNameInput.value.trim(),
                default_condition: profileConditionSelect.value,
            }),
        });
        participantInput.value = data.participant_id;
        displayNameInput.value = data.display_name;
        conditionSelect.value = data.default_condition;
        showToast("User profile saved.");
        await loadToday();
    } catch (error) {
        showToast(error.message, true);
    }
}

const dayNames = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

function selectedDays() {
    return [...document.querySelectorAll("#day-picker input:checked")].map((input) => Number(input.value));
}

function setSelectedDays(days) {
    const selected = new Set((days || []).map(Number));
    document.querySelectorAll("#day-picker input").forEach((input) => {
        input.checked = selected.has(Number(input.value));
    });
}

function resetScheduleForm() {
    document.getElementById("schedule-id").value = "";
    document.getElementById("schedule-title").value = "";
    document.getElementById("schedule-type").value = "medication";
    document.getElementById("schedule-time").value = "09:00";
    document.getElementById("schedule-condition").value = profileConditionSelect.value || "HIGH";
    document.getElementById("schedule-enabled").checked = true;
    document.getElementById("schedule-message").value = publicConfig?.reminders?.medication?.message || "";
    setSelectedDays([0, 1, 2, 3, 4, 5, 6]);
    document.getElementById("save-schedule").textContent = "Add reminder";
    document.getElementById("cancel-edit-schedule").hidden = true;
}

function schedulePayload() {
    const type = document.getElementById("schedule-type").value;
    const defaultReminder = publicConfig?.reminders?.[type];
    return {
        title: document.getElementById("schedule-title").value.trim() || defaultReminder?.title || "Reminder",
        reminder_type: type,
        time_of_day: document.getElementById("schedule-time").value,
        days_of_week: selectedDays(),
        message: document.getElementById("schedule-message").value.trim() || defaultReminder?.message || "It is time for your reminder.",
        condition_name: document.getElementById("schedule-condition").value,
        enabled: document.getElementById("schedule-enabled").checked,
    };
}

async function saveSchedule() {
    const id = document.getElementById("schedule-id").value;
    const payload = schedulePayload();
    try {
        if (id) {
            await api(`/api/schedules/${id}`, { method: "PUT", body: JSON.stringify(payload) });
            showToast("Reminder updated.");
        } else {
            await api("/api/schedules", { method: "POST", body: JSON.stringify(payload) });
            showToast("Reminder added to the timetable.");
        }
        resetScheduleForm();
        await Promise.all([loadSchedules(), loadToday()]);
    } catch (error) {
        showToast(error.message, true);
    }
}

function editSchedule(id) {
    const item = currentSchedules.find((schedule) => schedule.id === Number(id));
    if (!item) return;
    document.getElementById("schedule-id").value = item.id;
    document.getElementById("schedule-title").value = item.title;
    document.getElementById("schedule-type").value = item.reminder_type;
    document.getElementById("schedule-time").value = item.time_of_day;
    document.getElementById("schedule-condition").value = item.condition_name;
    document.getElementById("schedule-enabled").checked = Boolean(item.enabled);
    document.getElementById("schedule-message").value = item.message;
    setSelectedDays(item.days_of_week);
    document.getElementById("save-schedule").textContent = "Save changes";
    document.getElementById("cancel-edit-schedule").hidden = false;
    document.querySelector(".schedule-form-card").scrollIntoView({ behavior: "smooth", block: "start" });
}

async function deleteSchedule(id) {
    const item = currentSchedules.find((schedule) => schedule.id === Number(id));
    if (!item || !window.confirm(`Delete "${item.title}"?`)) return;
    try {
        await api(`/api/schedules/${id}`, { method: "DELETE" });
        showToast("Reminder deleted.");
        await Promise.all([loadSchedules(), loadToday()]);
    } catch (error) {
        showToast(error.message, true);
    }
}

async function toggleSchedule(id) {
    const item = currentSchedules.find((schedule) => schedule.id === Number(id));
    if (!item) return;
    try {
        await api(`/api/schedules/${id}`, {
            method: "PUT",
            body: JSON.stringify({ ...item, enabled: !item.enabled }),
        });
        await Promise.all([loadSchedules(), loadToday()]);
    } catch (error) {
        showToast(error.message, true);
    }
}

async function triggerSchedule(id) {
    try {
        const data = await api(`/api/schedules/${id}/trigger`, { method: "POST", body: "{}" });
        closeDeveloperPanel();
        renderReminder(data.active_reminder, true);
    } catch (error) {
        showToast(error.message, true);
    }
}

function formatDays(days) {
    if ((days || []).length === 7) return "Every day";
    if (JSON.stringify(days) === JSON.stringify([0, 1, 2, 3, 4])) return "Weekdays";
    if (JSON.stringify(days) === JSON.stringify([5, 6])) return "Weekend";
    return (days || []).map((day) => dayNames[Number(day)]).join(" · ");
}

function formatTime(time) {
    if (!time) return "--:--";
    const [hour, minute] = time.split(":").map(Number);
    const date = new Date();
    date.setHours(hour, minute, 0, 0);
    return date.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
}

async function loadSchedules() {
    try {
        const data = await api("/api/schedules");
        currentSchedules = data.schedules || [];
        const list = document.getElementById("schedule-list");
        if (!currentSchedules.length) {
            list.innerHTML = '<p class="empty-state">No reminders yet. Add one above.</p>';
            return;
        }
        list.innerHTML = currentSchedules.map((item) => {
            const symbol = publicConfig?.reminders?.[item.reminder_type]?.symbol || "🔔";
            const enabledClass = item.enabled ? "" : " disabled";
            return `
                <article class="schedule-item${enabledClass}">
                    <div class="schedule-time-block">
                        <strong>${escapeHtml(formatTime(item.time_of_day))}</strong>
                        <span>${escapeHtml(formatDays(item.days_of_week))}</span>
                    </div>
                    <div class="schedule-info">
                        <div class="schedule-title-row">
                            <span class="schedule-symbol">${symbol}</span>
                            <strong>${escapeHtml(item.title)}</strong>
                            <span class="mode-badge">${escapeHtml(item.condition_name)}</span>
                        </div>
                        <p>${escapeHtml(item.message)}</p>
                    </div>
                    <div class="schedule-actions">
                        <button class="mini-action" data-schedule-action="trigger" data-id="${item.id}" type="button">Test now</button>
                        <button class="mini-action" data-schedule-action="edit" data-id="${item.id}" type="button">Edit</button>
                        <button class="mini-action" data-schedule-action="toggle" data-id="${item.id}" type="button">${item.enabled ? "Disable" : "Enable"}</button>
                        <button class="mini-action danger" data-schedule-action="delete" data-id="${item.id}" type="button">Delete</button>
                    </div>
                </article>
            `;
        }).join("");
    } catch (error) {
        showToast(`Could not load timetable: ${error.message}`, true);
    }
}

async function resetDemoSchedule() {
    if (!window.confirm("Replace the current timetable with the synthetic demonstration schedule?")) return;
    try {
        await api("/api/schedules/reset-demo", { method: "POST", body: "{}" });
        resetScheduleForm();
        await Promise.all([loadSchedules(), loadToday()]);
        showToast("Demo timetable restored.");
    } catch (error) {
        showToast(error.message, true);
    }
}

async function loadToday() {
    try {
        const data = await api("/api/today");
        const list = document.getElementById("today-list");
        const upcoming = data.upcoming || [];

        /*
            Compact robot-screen routine:

            Large card:
                next reminder

            Small list:
                following reminder
                reminder after that

            Maximum visible upcoming events = 3.
        */
        const laterUpcoming = upcoming.slice(1, 3);

        if (!upcoming.length) {
            list.innerHTML =
                '<p class="empty-state compact-empty">No more reminders today.</p>';
        } else if (!laterUpcoming.length) {
            list.innerHTML =
                '<p class="empty-state compact-empty">No other reminders today.</p>';
        } else {
            list.innerHTML = laterUpcoming.map((item) => {
                const symbol =
                    publicConfig?.reminders?.[item.reminder_type]?.symbol || "🔔";

                return `
                    <div class="today-item">
                        <span class="today-time">${escapeHtml(formatTime(item.time_of_day))}</span>
                        <span class="today-symbol">${symbol}</span>
                        <span class="today-title">${escapeHtml(item.title)}</span>
                    </div>
                `;
            }).join("");
        }

        const next = data.next;
        if (next) {
            const symbol = publicConfig?.reminders?.[next.reminder_type]?.symbol || "🔔";
            document.getElementById("next-reminder-symbol").textContent = symbol;
            document.getElementById("next-reminder-title").textContent = next.title;
            document.getElementById("next-reminder-time").textContent = formatTime(next.time_of_day);
        } else {
            document.getElementById("next-reminder-symbol").textContent = "✅";
            document.getElementById("next-reminder-title").textContent = "Nothing scheduled";
            document.getElementById("next-reminder-time").textContent = "You're all caught up";
        }
    } catch (error) {
        console.warn("Today's schedule unavailable:", error);
    }
}

async function loadTrials() {
    try {
        const data = await api("/api/trials?limit=14");
        document.getElementById("trial-count").textContent = data.count;
        const body = document.getElementById("trial-table-body");
        if (!data.trials.length) {
            body.innerHTML = '<tr><td colspan="6">No interactions yet.</td></tr>';
            return;
        }
        body.innerHTML = data.trials.map((trial) => `
            <tr>
                <td>${trial.id}</td>
                <td>${escapeHtml(trial.participant_id)}</td>
                <td>${escapeHtml(trial.action || "acknowledged")}</td>
                <td>${escapeHtml(trial.reminder_type)}</td>
                <td>${escapeHtml(trial.condition_name)}</td>
                <td>${(trial.response_time_ms / 1000).toFixed(2)} s</td>
            </tr>
        `).join("");
    } catch (error) {
        showToast(`Could not load interactions: ${error.message}`, true);
    }
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
            renderReminder(data.active_reminder, true);
        } else if (data.mode === "acknowledgement" && data.last_result) {
            clearReminderFollowupTimer();
            if (!screens.acknowledgement.classList.contains("active")) {
                renderAcknowledgement(data.last_result, data.active_reminder?.condition?.name || "LOW", false);
            }
        } else if (data.mode === "idle" && !screens.idle.classList.contains("active")) {
            clearReminderFollowupTimer();
            currentReminderKey = null;
            showScreen("idle");
        }
    } catch (error) {
        console.warn("State sync failed:", error);
    }
}

async function initialise() {
    updateClock();
    setInterval(updateClock, 1000);
    startIdleAnimations();

    try {
        publicConfig = await api("/api/config");
        document.getElementById("hardware-mode").textContent = `${publicConfig.hardware_mode} hardware`;
        participantInput.value = publicConfig.profile.participant_id || "P001";
        displayNameInput.value = publicConfig.profile.display_name || "";
        profileConditionSelect.value = publicConfig.profile.default_condition || "HIGH";
        conditionSelect.value = publicConfig.profile.default_condition || "HIGH";
        resetScheduleForm();
        updateCueSummary();
        await Promise.all([syncState(), loadToday()]);

        const pollMs = Math.max(500, Number(document.body.dataset.pollSeconds || 1) * 1000);
        setInterval(syncState, pollMs);
        setInterval(loadToday, 60000);
    } catch (error) {
        showToast(`Startup error: ${error.message}`, true);
    }
}

document.getElementById("developer-toggle").addEventListener("click", openDeveloperPanel);
document.getElementById("developer-close").addEventListener("click", closeDeveloperPanel);
panelBackdrop.addEventListener("click", closeDeveloperPanel);
triggerButton.addEventListener("click", triggerReminder);
acknowledgeButton.addEventListener("click", acknowledgeReminder);
snoozeButton.addEventListener("click", snoozeReminder);
conditionSelect.addEventListener("change", updateCueSummary);
document.getElementById("save-profile").addEventListener("click", saveProfile);
document.getElementById("save-schedule").addEventListener("click", saveSchedule);
document.getElementById("cancel-edit-schedule").addEventListener("click", resetScheduleForm);
document.getElementById("reset-demo-schedule").addEventListener("click", resetDemoSchedule);

document.getElementById("schedule-type").addEventListener("change", (event) => {
    const type = event.target.value;
    const reminder = publicConfig?.reminders?.[type];
    if (!reminder) return;
    if (!document.getElementById("schedule-title").value.trim()) {
        document.getElementById("schedule-title").value = reminder.title;
    }
    document.getElementById("schedule-message").value = reminder.message;
});

document.querySelectorAll(".quick-talk-button").forEach((button) => {
    button.addEventListener("click", () => companionInteraction(button.dataset.intent));
});

document.querySelectorAll(".hardware-test").forEach((button) => {
    button.addEventListener("click", () => testHardware(button.dataset.action));
});

document.getElementById("schedule-list").addEventListener("click", (event) => {
    const button = event.target.closest("[data-schedule-action]");
    if (!button) return;
    const id = Number(button.dataset.id);
    const action = button.dataset.scheduleAction;
    if (action === "trigger") triggerSchedule(id);
    if (action === "edit") editSchedule(id);
    if (action === "toggle") toggleSchedule(id);
    if (action === "delete") deleteSchedule(id);
});

document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && developerPanel.classList.contains("open")) closeDeveloperPanel();
});

initialise();
