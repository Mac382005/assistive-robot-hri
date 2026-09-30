/* HRI Socially Assistive Robot V3
   Multi-profile management + persistent companion chat.
   Loaded AFTER robot.js so it can reuse the existing face/speech functions.
*/

let v3Profiles = [];
let v3ActiveProfileId = null;
let v3AIStatus = null;

function v3CreateUI() {
    if (document.getElementById("v3-profile-select")) return;

    const topActions = document.querySelector(".top-actions");
    if (topActions) {
        const switcher = document.createElement("div");
        switcher.className = "v3-profile-switcher";
        switcher.innerHTML = `
            <span class="v3-profile-icon">👤</span>
            <select id="v3-profile-select" aria-label="Active user profile"></select>
        `;
        topActions.insertBefore(switcher, topActions.firstChild);

        const chatButton = document.createElement("button");
        chatButton.id = "v3-chat-open";
        chatButton.className = "v3-chat-button";
        chatButton.type = "button";
        chatButton.innerHTML = `<span>💬</span><span>Chat</span>`;
        topActions.insertBefore(chatButton, document.getElementById("hardware-mode")?.parentElement || null);
    }

    const developerHeader = document.querySelector(".developer-header");
    if (developerHeader) {
        const profileSection = document.createElement("section");
        profileSection.id = "v3-profile-manager";
        profileSection.className = "panel-section v3-profile-manager";
        profileSection.innerHTML = `
            <div class="section-heading-row">
                <div>
                    <h3>Profiles</h3>
                    <p class="panel-note">Only one profile is active at a time. Each profile has its own timetable, trials and chat history.</p>
                </div>
                <span id="v3-active-profile-badge" class="v3-active-badge">Active</span>
            </div>

            <div id="v3-profile-list" class="v3-profile-list"></div>

            <details class="v3-add-profile-box">
                <summary>＋ Add another profile</summary>
                <div class="v3-add-profile-form">
                    <div class="form-grid three-col">
                        <label>
                            User ID
                            <input id="v3-new-profile-id" type="text" placeholder="P002" maxlength="30">
                        </label>
                        <label>
                            Display name
                            <input id="v3-new-profile-name" type="text" placeholder="Mary" maxlength="40">
                        </label>
                        <label>
                            Social mode
                            <select id="v3-new-profile-condition">
                                <option value="HIGH">HIGH — social companion</option>
                                <option value="LOW">LOW — simple reminder</option>
                            </select>
                        </label>
                    </div>
                    <label class="v3-wide-label">
                        About me / interests (optional)
                        <textarea id="v3-new-profile-about" rows="2" maxlength="500" placeholder="e.g. Enjoys gardening, jazz and old movies"></textarea>
                    </label>
                    <label class="v3-check-row">
                        <input id="v3-copy-demo-schedule" type="checkbox" checked>
                        Start this profile with the synthetic demo timetable
                    </label>
                    <button id="v3-create-profile" class="secondary-button" type="button">Create profile</button>
                </div>
            </details>
        `;
        developerHeader.insertAdjacentElement("afterend", profileSection);
    }

    // Add editable About Me field to the existing active-profile editor.
    const existingProfileSection = [...document.querySelectorAll(".panel-section")].find(
        (section) => section.querySelector("h3")?.textContent?.trim() === "User profile"
    );
    if (existingProfileSection && !document.getElementById("v3-about-me")) {
        const aboutLabel = document.createElement("label");
        aboutLabel.className = "v3-about-label";
        aboutLabel.innerHTML = `
            About me / interests
            <textarea id="v3-about-me" rows="2" maxlength="500" placeholder="Optional non-sensitive notes to make conversation more personal"></textarea>
        `;
        const grid = existingProfileSection.querySelector(".form-grid");
        grid?.insertAdjacentElement("afterend", aboutLabel);
    }

    const chatBackdrop = document.createElement("div");
    chatBackdrop.id = "v3-chat-backdrop";
    chatBackdrop.className = "v3-chat-backdrop";

    const chatDrawer = document.createElement("aside");
    chatDrawer.id = "v3-chat-drawer";
    chatDrawer.className = "v3-chat-drawer";
    chatDrawer.setAttribute("aria-hidden", "true");
    chatDrawer.innerHTML = `
        <header class="v3-chat-header">
            <div>
                <p class="eyebrow">Companion conversation · V3</p>
                <h2>Talk with your robot</h2>
                <div class="v3-ai-status-row">
                    <span id="v3-ai-dot" class="v3-ai-dot"></span>
                    <span id="v3-ai-status">Checking AI…</span>
                </div>
            </div>
            <button id="v3-chat-close" class="icon-button" type="button" aria-label="Close chat">×</button>
        </header>

        <div class="v3-chat-notice">
            Conversation history is kept separately for the active profile. The robot can chat casually, but it should not be used to make medication or medical decisions.
        </div>

        <div id="v3-chat-messages" class="v3-chat-messages" aria-live="polite"></div>

        <div class="v3-chat-compose">
            <textarea id="v3-chat-input" rows="2" maxlength="600" placeholder="Type something to your companion…"></textarea>
            <button id="v3-chat-send" class="primary-button v3-send-button" type="button">Send</button>
        </div>

        <div class="v3-chat-footer">
            <span id="v3-chat-profile-name">Active profile</span>
            <button id="v3-chat-clear" class="mini-action" type="button">Clear chat history</button>
        </div>
    `;

    document.body.append(chatBackdrop, chatDrawer);
}

function v3RenderProfiles(data) {
    v3Profiles = data.profiles || [];
    v3ActiveProfileId = Number(data.active_profile_id);

    const select = document.getElementById("v3-profile-select");
    if (select) {
        select.innerHTML = v3Profiles.map((item) => {
            const label = item.display_name || item.participant_id;
            return `<option value="${item.id}">${escapeHtml(label)}</option>`;
        }).join("");
        select.value = String(v3ActiveProfileId);
    }

    const list = document.getElementById("v3-profile-list");
    if (list) {
        list.innerHTML = v3Profiles.map((item) => {
            const active = Number(item.id) === v3ActiveProfileId;
            const label = item.display_name || item.participant_id;
            return `
                <article class="v3-profile-card${active ? " active" : ""}">
                    <div class="v3-profile-avatar">${active ? "😊" : "👤"}</div>
                    <div class="v3-profile-card-info">
                        <strong>${escapeHtml(label)}</strong>
                        <span>${escapeHtml(item.participant_id)}</span>
                        ${item.about_me ? `<small>${escapeHtml(item.about_me)}</small>` : ""}
                    </div>
                    <div class="v3-profile-card-actions">
                        ${active
                            ? `<span class="v3-current-label">In use</span>`
                            : `<button class="mini-action" data-v3-profile-action="activate" data-id="${item.id}" type="button">Use profile</button>`}
                        <button class="mini-action danger" data-v3-profile-action="delete" data-id="${item.id}" type="button" ${v3Profiles.length <= 1 ? "disabled" : ""}>Delete</button>
                    </div>
                </article>
            `;
        }).join("");
    }

    const active = v3Profiles.find((item) => Number(item.id) === v3ActiveProfileId);
    if (active) {
        const badge = document.getElementById("v3-active-profile-badge");
        if (badge) badge.textContent = `Active: ${active.display_name || active.participant_id}`;
        const about = document.getElementById("v3-about-me");
        if (about) about.value = active.about_me || "";
        const chatName = document.getElementById("v3-chat-profile-name");
        if (chatName) chatName.textContent = `Chat history: ${active.display_name || active.participant_id}`;
    }
}

async function v3LoadProfiles() {
    const data = await api("/api/profiles");
    v3RenderProfiles(data);
    return data;
}

async function v3RefreshActiveProfile() {
    publicConfig = await api("/api/config");
    participantInput.value = publicConfig.profile.participant_id || "P001";
    displayNameInput.value = publicConfig.profile.display_name || "";
    profileConditionSelect.value = publicConfig.profile.default_condition || "HIGH";
    conditionSelect.value = publicConfig.profile.default_condition || "HIGH";
    const about = document.getElementById("v3-about-me");
    if (about) about.value = publicConfig.profile.about_me || "";
    updateCueSummary();
}

async function v3ActivateProfile(profileId) {
    try {
        const result = await api(`/api/profiles/${profileId}/activate`, {
            method: "POST",
            body: "{}",
        });
        await Promise.all([
            v3LoadProfiles(),
            v3RefreshActiveProfile(),
            loadSchedules(),
            loadToday(),
            loadTrials(),
            v3LoadChatHistory(),
        ]);
        resetScheduleForm();
        setIdleSpeech(`Hello${result.profile.display_name ? ", " + result.profile.display_name : ""}. Your profile is now active.`);
        setFaceExpression(idleFace, "happy");
        popEmoji("👤");
        showToast("Profile switched. This user's timetable is now active.");
    } catch (error) {
        showToast(error.message, true);
    }
}

async function v3CreateProfile() {
    const participantId = document.getElementById("v3-new-profile-id").value.trim();
    const displayName = document.getElementById("v3-new-profile-name").value.trim();
    const condition = document.getElementById("v3-new-profile-condition").value;
    const aboutMe = document.getElementById("v3-new-profile-about").value.trim();
    const copyDemo = document.getElementById("v3-copy-demo-schedule").checked;
    if (!participantId) {
        showToast("Enter a User ID first.", true);
        return;
    }
    try {
        const created = await api("/api/profiles", {
            method: "POST",
            body: JSON.stringify({
                participant_id: participantId,
                display_name: displayName,
                default_condition: condition,
                about_me: aboutMe,
                copy_demo_schedule: copyDemo,
            }),
        });
        document.getElementById("v3-new-profile-id").value = "";
        document.getElementById("v3-new-profile-name").value = "";
        document.getElementById("v3-new-profile-about").value = "";
        await v3LoadProfiles();
        showToast(`Profile ${created.display_name || created.participant_id} created.`);
    } catch (error) {
        showToast(error.message, true);
    }
}

async function v3DeleteProfile(profileId) {
    const item = v3Profiles.find((profile) => Number(profile.id) === Number(profileId));
    if (!item) return;
    if (!window.confirm(`Delete profile "${item.display_name || item.participant_id}" and its timetable/chat history?`)) return;
    try {
        await api(`/api/profiles/${profileId}`, { method: "DELETE" });
        await Promise.all([v3LoadProfiles(), v3RefreshActiveProfile(), loadSchedules(), loadToday(), loadTrials(), v3LoadChatHistory()]);
        showToast("Profile deleted.");
    } catch (error) {
        showToast(error.message, true);
    }
}

async function v3SaveActiveProfile(event) {
    event.preventDefault();
    event.stopImmediatePropagation();
    try {
        const data = await api("/api/profile", {
            method: "PUT",
            body: JSON.stringify({
                participant_id: participantInput.value.trim() || "P001",
                display_name: displayNameInput.value.trim(),
                default_condition: profileConditionSelect.value,
                about_me: document.getElementById("v3-about-me")?.value.trim() || "",
            }),
        });
        publicConfig.profile = data;
        conditionSelect.value = data.default_condition;
        await v3LoadProfiles();
        showToast("Active profile saved.");
    } catch (error) {
        showToast(error.message, true);
    }
}

function v3OpenChat() {
    document.getElementById("v3-chat-drawer")?.classList.add("open");
    document.getElementById("v3-chat-backdrop")?.classList.add("show");
    document.getElementById("v3-chat-drawer")?.setAttribute("aria-hidden", "false");
    v3LoadChatHistory();
    setTimeout(() => document.getElementById("v3-chat-input")?.focus(), 120);
}

function v3CloseChat() {
    document.getElementById("v3-chat-drawer")?.classList.remove("open");
    document.getElementById("v3-chat-backdrop")?.classList.remove("show");
    document.getElementById("v3-chat-drawer")?.setAttribute("aria-hidden", "true");
}

function v3AppendMessage(role, content) {
    const box = document.getElementById("v3-chat-messages");
    if (!box) return;
    if (box.querySelector(".v3-chat-empty")) box.innerHTML = "";
    const message = document.createElement("div");
    message.className = `v3-message ${role}`;
    message.innerHTML = `
        <span class="v3-message-label">${role === "user" ? "You" : "Robot"}</span>
        <div>${escapeHtml(content)}</div>
    `;
    box.appendChild(message);
    box.scrollTop = box.scrollHeight;
}

async function v3LoadChatHistory() {
    const box = document.getElementById("v3-chat-messages");
    if (!box) return;
    try {
        const data = await api("/api/chat/history?limit=40");
        box.innerHTML = "";
        const chatName = document.getElementById("v3-chat-profile-name");
        if (chatName) chatName.textContent = `Chat history: ${data.profile.display_name || data.profile.participant_id}`;
        if (!(data.messages || []).length) {
            box.innerHTML = `<div class="v3-chat-empty">No conversation yet. Say hello or ask about the day.</div>`;
            return;
        }
        data.messages.forEach((item) => v3AppendMessage(item.role, item.content));
    } catch (error) {
        console.warn("Chat history unavailable:", error);
    }
}

async function v3LoadAIStatus() {
    try {
        v3AIStatus = await api("/api/ai/status");
        const label = document.getElementById("v3-ai-status");
        const dot = document.getElementById("v3-ai-dot");
        if (v3AIStatus.api_available && !v3AIStatus.last_error) {
            label.textContent = `Cloud AI configured · ${v3AIStatus.model}`;
            dot.classList.add("online");
        } else if (v3AIStatus.api_available && v3AIStatus.last_error) {
            label.textContent = "Cloud AI configured · last request used fallback";
            dot.classList.remove("online");
        } else {
            label.textContent = "Basic conversation mode · add API key for open-ended chat";
            dot.classList.remove("online");
        }
    } catch (error) {
        document.getElementById("v3-ai-status").textContent = "AI status unavailable";
    }
}

async function v3SendChat() {
    const input = document.getElementById("v3-chat-input");
    const button = document.getElementById("v3-chat-send");
    const message = input.value.trim();
    if (!message) return;
    input.value = "";
    v3AppendMessage("user", message);
    button.disabled = true;
    button.textContent = "Thinking…";

    try {
        const data = await api("/api/chat", {
            method: "POST",
            body: JSON.stringify({ message }),
        });
        v3AppendMessage("assistant", data.text);
        setIdleSpeech(data.text);
        setFaceExpression(idleFace, data.expression || "happy");
        popEmoji(data.emoji || "💬");
        speak(data.text, idleFace, data.expression || "happy");
        v3AIStatus = data.ai_status || v3AIStatus;
        await v3LoadAIStatus();
    } catch (error) {
        v3AppendMessage("assistant", "Sorry, I could not answer that just now.");
        showToast(error.message, true);
    } finally {
        button.disabled = false;
        button.textContent = "Send";
        input.focus();
    }
}

async function v3ClearChat() {
    if (!window.confirm("Clear the chat history for this profile?")) return;
    try {
        await api("/api/chat/history", { method: "DELETE" });
        await v3LoadChatHistory();
        showToast("Chat history cleared for this profile.");
    } catch (error) {
        showToast(error.message, true);
    }
}

function v3BindEvents() {
    document.getElementById("v3-profile-select")?.addEventListener("change", (event) => {
        v3ActivateProfile(Number(event.target.value));
    });
    document.getElementById("v3-create-profile")?.addEventListener("click", v3CreateProfile);
    document.getElementById("v3-profile-list")?.addEventListener("click", (event) => {
        const button = event.target.closest("[data-v3-profile-action]");
        if (!button) return;
        const id = Number(button.dataset.id);
        if (button.dataset.v3ProfileAction === "activate") v3ActivateProfile(id);
        if (button.dataset.v3ProfileAction === "delete") v3DeleteProfile(id);
    });

    // Capture phase prevents the old V2 save handler from firing first.
    document.getElementById("save-profile")?.addEventListener("click", v3SaveActiveProfile, true);

    document.getElementById("v3-chat-open")?.addEventListener("click", v3OpenChat);
    document.getElementById("v3-chat-close")?.addEventListener("click", v3CloseChat);
    document.getElementById("v3-chat-backdrop")?.addEventListener("click", v3CloseChat);
    document.getElementById("v3-chat-send")?.addEventListener("click", v3SendChat);
    document.getElementById("v3-chat-clear")?.addEventListener("click", v3ClearChat);
    document.getElementById("v3-chat-input")?.addEventListener("keydown", (event) => {
        if (event.key === "Enter" && !event.shiftKey) {
            event.preventDefault();
            v3SendChat();
        }
    });
}

async function v3Initialise() {
    v3CreateUI();
    v3BindEvents();
    try {
        await Promise.all([v3LoadProfiles(), v3LoadAIStatus()]);
        await v3RefreshActiveProfile();
    } catch (error) {
        showToast(`V3 startup: ${error.message}`, true);
    }
}

// robot.js begins its own async initialisation first. Give it a short head-start.
window.setTimeout(v3Initialise, 350);
