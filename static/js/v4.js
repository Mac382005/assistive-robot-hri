/*
 * HRI Socially Assistive Robot V4.1
 * Voice-first, face-first interaction layer.
 *
 * V4.1 changes:
 * - explicit two-tap conversation capture: tap once to start, tap again to finish
 * - no automatic response on a short pause
 * - conversation history is visible in the full-screen Control Centre
 * - selectable browser/system TTS voice with a saved preference
 */

(() => {
    "use strict";

    const SpeechRecognitionClass =
        window.SpeechRecognition || window.webkitSpeechRecognition || null;

    const VOICE_STORAGE_KEY = "hri_robot_voice_name";

    let recognition = null;
    let recognitionActive = false;
    let voiceSessionActive = false;
    let isThinking = false;
    let submitAfterRecognitionEnds = false;
    let fatalRecognitionError = false;
    let restartTimer = null;
    let finishFallbackTimer = null;
    let sessionFinalParts = [];
    let sessionInterim = "";

    function el(id) {
        return document.getElementById(id);
    }

    function setVoiceStatus(message, state = "idle") {
        const status = el("v4-voice-status");
        const dock = el("v4-voice-dock");
        if (status) status.textContent = message;
        if (dock) {
            dock.dataset.state = state;
            dock.classList.toggle("busy", state === "thinking" || state === "speaking");
        }
        updateMicButton(state);
    }

    function updateMicButton(state = "idle") {
        const button = el("v4-mic-button");
        const icon = button?.querySelector(".v4-mic-icon");
        if (!button || !icon) return;

        if (voiceSessionActive || state === "listening") {
            icon.textContent = "✓";
            button.setAttribute("aria-label", "Finish speaking and send to the robot");
            button.title = "Finish speaking";
        } else {
            icon.textContent = "🎙";
            button.setAttribute("aria-label", "Start talking to the robot");
            button.title = "Start talking";
        }
    }

    function setTranscript(message = "") {
        const transcript = el("v4-live-transcript");
        if (!transcript) return;
        transcript.textContent = message;
        transcript.hidden = !message;
    }

    function idlePrompt() {
        return SpeechRecognitionClass
            ? "Tap my face or the microphone to start talking."
            : "Voice input needs a supported Chrome or Edge browser.";
    }

    function listeningPrompt() {
        return "I’m listening… Tap my face again when you’ve finished.";
    }

    function showVoiceError(message) {
        setVoiceStatus(message, "error");
        if (typeof showToast === "function") {
            showToast(message, true);
        }
    }

    function clearTimers() {
        if (restartTimer) {
            window.clearTimeout(restartTimer);
            restartTimer = null;
        }
        if (finishFallbackTimer) {
            window.clearTimeout(finishFallbackTimer);
            finishFallbackTimer = null;
        }
    }

    function stopRecognition(abort = false) {
        if (!recognition) return;
        try {
            if (abort && recognition.abort) recognition.abort();
            else recognition.stop();
        } catch (error) {
            console.debug("Voice recognition stop ignored:", error);
        }
    }

    function cancelVoiceSession() {
        clearTimers();
        voiceSessionActive = false;
        submitAfterRecognitionEnds = false;
        fatalRecognitionError = false;
        sessionFinalParts = [];
        sessionInterim = "";
        stopRecognition(true);
        recognitionActive = false;
        setListeningVisual(false);
        setTranscript("");
        if (!isThinking) setVoiceStatus(idlePrompt(), "idle");
    }

    function stopRobotSpeech() {
        if ("speechSynthesis" in window && window.speechSynthesis.speaking) {
            window.speechSynthesis.cancel();
        }
    }

    function setListeningVisual(active) {
        document.body.classList.toggle("v4-listening", active);
        if (active) {
            if (typeof setFaceExpression === "function" && el("robot-face")) {
                setFaceExpression(el("robot-face"), "attentive");
            }
        } else if (!isThinking && typeof setFaceExpression === "function" && el("robot-face")) {
            setFaceExpression(el("robot-face"), "happy");
        }
        updateMicButton(active ? "listening" : "idle");
    }

    function currentSessionText() {
        return [...sessionFinalParts, sessionInterim]
            .join(" ")
            .replace(/\s+/g, " ")
            .trim();
    }

    function updateVisibleTranscript() {
        const text = currentSessionText();
        setTranscript(text ? `You: ${text}` : "");
    }

    async function sendVoiceMessage(message) {
        const cleaned = String(message || "").trim();
        if (!cleaned || isThinking) return;

        isThinking = true;
        voiceSessionActive = false;
        submitAfterRecognitionEnds = false;
        setListeningVisual(false);
        setTranscript(`You: ${cleaned}`);
        setVoiceStatus("Thinking…", "thinking");

        if (typeof setIdleSpeech === "function") {
            setIdleSpeech("…");
        }
        if (typeof setFaceExpression === "function" && el("robot-face")) {
            setFaceExpression(el("robot-face"), "attentive");
        }

        try {
            const data = await api("/api/chat", {
                method: "POST",
                body: JSON.stringify({ message: cleaned }),
            });

            setTranscript("");
            if (typeof setIdleSpeech === "function") setIdleSpeech(data.text);
            if (typeof setFaceExpression === "function" && el("robot-face")) {
                setFaceExpression(el("robot-face"), data.expression || "happy");
            }
            if (typeof popEmoji === "function") popEmoji(data.emoji || "💬");

            setVoiceStatus("Speaking", "speaking");
            if (typeof speak === "function") {
                speak(data.text, el("robot-face"), data.expression || "happy");
            }

            // Keep the Control Centre history current even though the user-facing
            // typed chat has been removed.
            loadConversationHistory(false);

            const words = String(data.text || "").trim().split(/\s+/).filter(Boolean).length;
            const estimatedSpeechMs = Math.max(1800, Math.min(12000, words * 430));
            window.setTimeout(() => {
                if (!voiceSessionActive && !isThinking) {
                    setVoiceStatus(idlePrompt(), "idle");
                }
            }, estimatedSpeechMs);
        } catch (error) {
            console.error("Voice companion request failed:", error);
            if (typeof setIdleSpeech === "function") {
                setIdleSpeech("Sorry, I could not answer that just now.");
            }
            showVoiceError(error.message || "I could not answer that just now.");
        } finally {
            isThinking = false;
        }
    }

    function finaliseVoiceSession() {
        if (!submitAfterRecognitionEnds) return;

        clearTimers();
        submitAfterRecognitionEnds = false;
        voiceSessionActive = false;
        recognitionActive = false;
        setListeningVisual(false);

        const message = currentSessionText();
        sessionFinalParts = [];
        sessionInterim = "";

        if (!message) {
            setTranscript("");
            setVoiceStatus("I didn’t hear anything. Tap and try again.", "idle");
            return;
        }

        sendVoiceMessage(message);
    }

    function startRecognitionEngine() {
        if (!recognition || recognitionActive || !voiceSessionActive || fatalRecognitionError) return;

        try {
            recognition.start();
        } catch (error) {
            console.debug("Recognition start retry:", error);
            restartTimer = window.setTimeout(() => {
                restartTimer = null;
                if (voiceSessionActive && !recognitionActive && !isThinking && !fatalRecognitionError) {
                    try {
                        recognition.start();
                    } catch (retryError) {
                        showVoiceError("The microphone is still busy. Please try again.");
                        voiceSessionActive = false;
                        setListeningVisual(false);
                    }
                }
            }, 250);
        }
    }

    function startVoiceSession() {
        if (!SpeechRecognitionClass || !recognition) {
            showVoiceError("Voice recognition is unavailable in this browser.");
            return;
        }
        if (isThinking) return;
        if (!el("idle-screen")?.classList.contains("active")) return;
        if (el("developer-panel")?.classList.contains("open")) return;

        stopRobotSpeech();
        clearTimers();
        fatalRecognitionError = false;
        submitAfterRecognitionEnds = false;
        sessionFinalParts = [];
        sessionInterim = "";
        voiceSessionActive = true;

        setTranscript("");
        setListeningVisual(true);
        setVoiceStatus(listeningPrompt(), "listening");
        if (typeof setIdleSpeech === "function") {
            setIdleSpeech("I’m listening.");
        }

        startRecognitionEngine();
    }

    function finishVoiceSession() {
        if (!voiceSessionActive || isThinking) return;

        voiceSessionActive = false;
        submitAfterRecognitionEnds = true;
        setVoiceStatus("Got it — finishing your sentence…", "finishing");

        // Stop asks Chromium to emit its last final recognition result before
        // onend. We submit only after onend so the final words are not cut off.
        stopRecognition(false);

        if (!recognitionActive) {
            window.setTimeout(finaliseVoiceSession, 80);
            return;
        }

        // Defensive fallback for browsers that fail to fire onend promptly.
        finishFallbackTimer = window.setTimeout(() => {
            finaliseVoiceSession();
        }, 1200);
    }

    function toggleVoiceSession() {
        if (voiceSessionActive) finishVoiceSession();
        else startVoiceSession();
    }

    function configureRecognition() {
        const micButton = el("v4-mic-button");

        if (!SpeechRecognitionClass) {
            if (micButton) {
                micButton.disabled = true;
                micButton.setAttribute("aria-label", "Voice recognition is unavailable in this browser");
            }
            setVoiceStatus(idlePrompt(), "unsupported");
            return;
        }

        recognition = new SpeechRecognitionClass();
        // Continuous mode plus auto-restart lets the person pause naturally.
        // Crucially, results are NEVER sent until the second tap.
        recognition.continuous = true;
        recognition.interimResults = true;
        recognition.maxAlternatives = 1;
        recognition.lang = /^en/i.test(navigator.language || "")
            ? navigator.language
            : "en-AU";

        recognition.onstart = () => {
            recognitionActive = true;
            if (voiceSessionActive) {
                setListeningVisual(true);
                setVoiceStatus(listeningPrompt(), "listening");
            }
        };

        recognition.onresult = (event) => {
            let newFinalText = "";
            let latestInterim = "";

            for (let index = event.resultIndex; index < event.results.length; index += 1) {
                const result = event.results[index];
                const text = String(result[0]?.transcript || "").trim();
                if (!text) continue;

                if (result.isFinal) {
                    newFinalText += `${newFinalText ? " " : ""}${text}`;
                } else {
                    latestInterim = text;
                }
            }

            if (newFinalText) sessionFinalParts.push(newFinalText);
            sessionInterim = latestInterim;
            updateVisibleTranscript();
        };

        recognition.onerror = (event) => {
            recognitionActive = false;
            const code = event.error || "unknown";

            if (code === "aborted") return;

            if (code === "no-speech") {
                // A pause is no longer treated as the end of the user's turn.
                if (voiceSessionActive) {
                    setVoiceStatus(listeningPrompt(), "listening");
                }
                return;
            }

            if (code === "not-allowed" || code === "service-not-allowed") {
                fatalRecognitionError = true;
                voiceSessionActive = false;
                submitAfterRecognitionEnds = false;
                setListeningVisual(false);
                showVoiceError("Microphone permission is blocked. Allow microphone access, then try again.");
                return;
            }

            if (code === "network") {
                fatalRecognitionError = true;
                voiceSessionActive = false;
                submitAfterRecognitionEnds = false;
                setListeningVisual(false);
                showVoiceError("Voice recognition could not reach its speech service.");
                return;
            }

            fatalRecognitionError = true;
            voiceSessionActive = false;
            submitAfterRecognitionEnds = false;
            setListeningVisual(false);
            showVoiceError(`Voice recognition error: ${code}`);
        };

        recognition.onend = () => {
            recognitionActive = false;

            if (submitAfterRecognitionEnds) {
                finaliseVoiceSession();
                return;
            }

            if (voiceSessionActive && !isThinking && !fatalRecognitionError) {
                // Some Chromium builds end a recognition chunk after silence even
                // with continuous=true. Restart while the explicit session remains
                // open so a thinking pause does not make the robot answer early.
                restartTimer = window.setTimeout(() => {
                    restartTimer = null;
                    startRecognitionEngine();
                }, 180);
                return;
            }

            if (!isThinking && !voiceSessionActive) {
                setListeningVisual(false);
                setVoiceStatus(idlePrompt(), "idle");
            }
        };
    }

    function formatHistoryTime(value) {
        if (!value) return "";
        const date = new Date(value);
        if (Number.isNaN(date.getTime())) return "";
        return date.toLocaleString([], {
            day: "numeric",
            month: "short",
            hour: "numeric",
            minute: "2-digit",
        });
    }

    async function loadConversationHistory(showErrors = true) {
        const list = el("v4-history-list");
        const count = el("v4-history-count");
        if (!list) return;

        try {
            const data = await api("/api/chat/history?limit=60");
            const messages = data.messages || [];
            if (count) count.textContent = `${messages.length} message${messages.length === 1 ? "" : "s"}`;

            if (!messages.length) {
                list.innerHTML = `<p class="v4-history-empty">No conversation yet for this profile.</p>`;
                return;
            }

            list.innerHTML = messages.map((item) => {
                const role = item.role === "assistant" ? "robot" : "user";
                const label = role === "robot" ? "Robot" : "User";
                const time = formatHistoryTime(item.created_at);
                return `
                    <article class="v4-history-message ${role}">
                        <div class="v4-history-meta">
                            <strong>${label}</strong>
                            <span>${escapeHtml(time)}</span>
                        </div>
                        <p>${escapeHtml(item.content)}</p>
                    </article>
                `;
            }).join("");

            list.scrollTop = list.scrollHeight;
        } catch (error) {
            console.warn("Conversation history unavailable:", error);
            if (showErrors && typeof showToast === "function") {
                showToast(`Could not load conversation history: ${error.message}`, true);
            }
        }
    }

    async function clearConversationHistory() {
        if (!window.confirm("Clear the conversation history for the active profile?")) return;
        try {
            await api("/api/chat/history", { method: "DELETE" });
            await loadConversationHistory(false);
            if (typeof showToast === "function") showToast("Conversation history cleared.");
        } catch (error) {
            if (typeof showToast === "function") showToast(error.message, true);
        }
    }

    function availableVoices() {
        if (!("speechSynthesis" in window)) return [];
        return window.speechSynthesis.getVoices()
            .filter((voice) => /^en/i.test(voice.lang || ""))
            .sort((a, b) => {
                const aNatural = /natural|online|aria|jenny|sonia|ava/i.test(a.name) ? 0 : 1;
                const bNatural = /natural|online|aria|jenny|sonia|ava/i.test(b.name) ? 0 : 1;
                return aNatural - bNatural || a.name.localeCompare(b.name);
            });
    }

    function populateVoiceSelector() {
        const select = el("v4-voice-select");
        const note = el("v4-voice-note");
        if (!select || !("speechSynthesis" in window)) return;

        const voices = availableVoices();
        if (!voices.length) {
            select.innerHTML = `<option value="">Waiting for browser voices…</option>`;
            if (note) note.textContent = "The browser has not reported its speech voices yet.";
            return;
        }

        let saved = "";
        try {
            saved = window.localStorage.getItem(VOICE_STORAGE_KEY) || "";
        } catch (_) {
            saved = "";
        }

        select.innerHTML = voices.map((voice) => {
            const natural = /natural|online/i.test(voice.name) ? " · Natural" : "";
            return `<option value="${escapeHtml(voice.name)}">${escapeHtml(voice.name)} — ${escapeHtml(voice.lang)}${natural}</option>`;
        }).join("");

        if (saved && voices.some((voice) => voice.name === saved)) {
            select.value = saved;
        } else {
            const recommended = voices.find((voice) =>
                /Microsoft Aria.*Natural|Microsoft Jenny.*Natural|Microsoft Sonia.*Natural|Microsoft Ava.*Natural/i.test(voice.name)
            ) || voices.find((voice) => /aria|jenny|sonia|ava/i.test(voice.name)) || voices[0];
            select.value = recommended.name;
        }

        if (note) {
            note.textContent = "Natural/online voices are preferred when your browser exposes them. Your choice is saved on this device.";
        }
    }

    function saveVoiceSelection() {
        const select = el("v4-voice-select");
        if (!select?.value) return;
        try {
            window.localStorage.setItem(VOICE_STORAGE_KEY, select.value);
        } catch (_) {
            // localStorage can be blocked in strict browser modes; the voice still
            // works for the current session through refreshPreferredSpeechVoice.
        }

        if (typeof refreshPreferredSpeechVoice === "function") {
            refreshPreferredSpeechVoice();
        }
        if (typeof showToast === "function") {
            showToast(`Robot voice set to ${select.value}.`);
        }
    }

    function testSelectedVoice() {
        saveVoiceSelection();
        if (typeof speak === "function") {
            speak(
                "Hello! It’s lovely to see you. I’m ready whenever you need me.",
                el("robot-face"),
                "happy"
            );
        }
    }

    function installControlCentreExtras() {
        if (el("v4-conversation-history")) return;

        const developerPanel = el("developer-panel");
        if (!developerPanel) return;

        const recentInteractions = [...developerPanel.querySelectorAll(".panel-section")].find(
            (section) => section.querySelector("h3")?.textContent?.trim() === "Recent interactions"
        );

        const voiceSection = document.createElement("section");
        voiceSection.id = "v4-voice-settings";
        voiceSection.className = "panel-section v4-control-extra";
        voiceSection.innerHTML = `
            <div class="section-heading-row">
                <div>
                    <h3>Robot voice</h3>
                    <p class="panel-note">Choose a voice installed or exposed by this browser. Natural voices are shown first when available.</p>
                </div>
            </div>
            <div class="v4-voice-settings-row">
                <label>
                    Voice
                    <select id="v4-voice-select" aria-label="Robot text-to-speech voice"></select>
                </label>
                <button id="v4-test-voice" class="secondary-button" type="button">Test voice</button>
            </div>
            <p id="v4-voice-note" class="panel-note">Loading available voices…</p>
        `;

        const historySection = document.createElement("section");
        historySection.id = "v4-conversation-history";
        historySection.className = "panel-section v4-control-extra";
        historySection.innerHTML = `
            <div class="section-heading-row">
                <div>
                    <h3>Conversation history</h3>
                    <p class="panel-note"><span id="v4-history-count">0 messages</span> · stored separately for the active profile</p>
                </div>
                <div class="v4-history-actions">
                    <button id="v4-history-refresh" class="secondary-button small" type="button">Refresh</button>
                    <button id="v4-history-clear" class="mini-action danger" type="button">Clear history</button>
                </div>
            </div>
            <div id="v4-history-list" class="v4-history-list" aria-live="polite">
                <p class="v4-history-empty">Loading conversation…</p>
            </div>
        `;

        const insertionPoint = recentInteractions || null;
        developerPanel.insertBefore(voiceSection, insertionPoint);
        developerPanel.insertBefore(historySection, insertionPoint);

        el("v4-history-refresh")?.addEventListener("click", () => loadConversationHistory(true));
        el("v4-history-clear")?.addEventListener("click", clearConversationHistory);
        el("v4-voice-select")?.addEventListener("change", saveVoiceSelection);
        el("v4-test-voice")?.addEventListener("click", testSelectedVoice);

        populateVoiceSelector();
        loadConversationHistory(false);

        if ("speechSynthesis" in window) {
            window.speechSynthesis.addEventListener("voiceschanged", populateVoiceSelector);
        }

        // V3 owns profile switching. Refresh this V4-only history once the
        // selected active profile has changed on the server.
        el("v3-profile-select")?.addEventListener("change", () => {
            window.setTimeout(() => loadConversationHistory(false), 650);
        });
    }

    function installVoiceUI() {
        if (el("v4-voice-dock")) return;

        document.body.classList.add("v4-voice-first");

        const idleScreen = el("idle-screen");
        if (!idleScreen) return;

        const dock = document.createElement("div");
        dock.id = "v4-voice-dock";
        dock.className = "v4-voice-dock";
        dock.dataset.state = "idle";
        dock.innerHTML = `
            <button id="v4-mic-button" class="v4-mic-button" type="button" aria-label="Start talking to the robot">
                <span class="v4-mic-icon" aria-hidden="true">🎙</span>
            </button>
            <div class="v4-voice-copy">
                <strong id="v4-voice-status">${idlePrompt()}</strong>
                <span id="v4-live-transcript" class="v4-live-transcript" hidden></span>
            </div>
        `;
        idleScreen.appendChild(dock);

        const controlButton = document.createElement("button");
        controlButton.id = "v4-control-centre-button";
        controlButton.className = "v4-control-centre-button";
        controlButton.type = "button";
        controlButton.setAttribute("aria-label", "Open full-screen control centre");
        controlButton.innerHTML = `<span aria-hidden="true">⚙</span><span class="v4-control-label">Controls</span>`;
        document.body.appendChild(controlButton);

        const developerClose = el("developer-close");
        if (developerClose) {
            developerClose.classList.add("v4-back-button");
            developerClose.innerHTML = `<span aria-hidden="true">←</span><span>Back to face</span>`;
            developerClose.setAttribute("aria-label", "Close control centre and return to robot face");
        }

        if (typeof setIdleSpeech === "function") {
            setIdleSpeech("Tap my face and talk to me.");
        }

        configureRecognition();

        el("v4-mic-button")?.addEventListener("click", (event) => {
            event.stopPropagation();
            toggleVoiceSession();
        });

        el("robot-face")?.addEventListener("click", toggleVoiceSession);
        el("robot-face")?.addEventListener("keydown", (event) => {
            if (event.key === "Enter" || event.key === " ") {
                event.preventDefault();
                toggleVoiceSession();
            }
        });
        el("robot-face")?.setAttribute("tabindex", "0");
        el("robot-face")?.setAttribute("role", "button");
        el("robot-face")?.setAttribute(
            "aria-label",
            "Robot face. Tap once to start talking and tap again when finished."
        );

        controlButton.addEventListener("click", () => {
            cancelVoiceSession();
            stopRobotSpeech();
            if (typeof openDeveloperPanel === "function") openDeveloperPanel();
        });

        const developerPanel = el("developer-panel");
        if (developerPanel) {
            const syncPanelState = () => {
                const open = developerPanel.classList.contains("open");
                document.body.classList.toggle("v4-control-centre-open", open);
                if (open) {
                    cancelVoiceSession();
                    stopRobotSpeech();
                    loadConversationHistory(false);
                    populateVoiceSelector();
                }
            };
            new MutationObserver(syncPanelState).observe(developerPanel, {
                attributes: true,
                attributeFilter: ["class"],
            });
            syncPanelState();
        }
    }

    function hideLegacyChatUI() {
        // The legacy typed-chat DOM remains because the V3 profile code still
        // references it, but V4 hides it from the participant-facing interface.
        document.body.classList.add("v4-chat-replaced-by-voice");
    }

    function initialiseV4() {
        hideLegacyChatUI();
        installVoiceUI();
        installControlCentreExtras();
    }

    // v3.js creates profile/chat elements after a short timeout. Waiting a little
    // longer lets V4.1 attach the Control Centre history and voice selector safely.
    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", () => {
            window.setTimeout(initialiseV4, 700);
        }, { once: true });
    } else {
        window.setTimeout(initialiseV4, 700);
    }
})();
