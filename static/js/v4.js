/*
 * HRI Socially Assistive Robot V4.3.2
 * Voice-first, face-first interaction layer with tablet audio capture.
 *
 * Input modes:
 * - Browser SpeechRecognition on supported desktop browsers.
 * - MediaRecorder + Gemini server-side transcription on tablets / unsupported browsers.
 *
 * Conversation is explicit two-tap:
 *   tap once -> listen/record
 *   tap again -> finish the full turn and send
 */

(() => {
    "use strict";

    const SpeechRecognitionClass =
        window.SpeechRecognition || window.webkitSpeechRecognition || null;

    const VOICE_STORAGE_KEY = "hri_robot_voice_name";

    let recognition = null;
    let recognitionActive = false;
    let voiceSessionActive = false;
    let voiceInputMode = null; // "recognition" | "recording"
    let isThinking = false;
    let submitAfterRecognitionEnds = false;
    let fatalRecognitionError = false;
    let restartTimer = null;
    let finishFallbackTimer = null;
    let sessionFinalParts = [];
    let sessionInterim = "";

    let mediaStream = null;
    let mediaRecorder = null;
    let mediaChunks = [];
    let recordingMimeType = "";
    let recordingStartedAt = 0;

    function el(id) {
        return document.getElementById(id);
    }

    function isIOSLike() {
        const ua = navigator.userAgent || "";
        return /iPad|iPhone|iPod/i.test(ua) ||
            (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);
    }

    function isAndroidLike() {
        return /Android/i.test(navigator.userAgent || "");
    }

    function recorderSupported() {
        return Boolean(
            window.isSecureContext &&
            navigator.mediaDevices?.getUserMedia &&
            window.MediaRecorder
        );
    }

    function setTabletAudioSession(type) {
        try {
            if (navigator.audioSession && "type" in navigator.audioSession) {
                navigator.audioSession.type = type;
                console.debug("[V4.3.2] audioSession ->", type);
            }
        } catch (error) {
            console.debug("Audio session change unavailable:", error);
        }
    }

    function preferredInputMode() {
        // Tablets use MediaRecorder because browser SpeechRecognition is
        // inconsistent on iPadOS and varies across Android browsers.
        if (recorderSupported() && (isIOSLike() || isAndroidLike() || !SpeechRecognitionClass)) {
            return "recording";
        }
        if (SpeechRecognitionClass) return "recognition";
        if (recorderSupported()) return "recording";
        return null;
    }

    function setVoiceStatus(message, state = "idle") {
        const status = el("v4-voice-status");
        const dock = el("v4-voice-dock");
        if (status) status.textContent = message;
        if (dock) {
            dock.dataset.state = state;
            dock.classList.toggle("busy", state === "thinking" || state === "speaking" || state === "transcribing");
        }
        updateMicButton(state);
    }

    function updateMicButton(state = "idle") {
        const button = el("v4-mic-button");
        const icon = button?.querySelector(".v4-mic-icon");
        if (!button || !icon) return;

        if (voiceSessionActive || state === "listening" || state === "recording") {
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
        const mode = preferredInputMode();
        if (mode === "recording") {
            return "Tap my face or microphone to talk.";
        }
        if (mode === "recognition") {
            return "Tap my face or microphone to start talking.";
        }
        if (!window.isSecureContext && (isIOSLike() || isAndroidLike())) {
            return "Voice needs the secure HTTPS tablet connection.";
        }
        return "Voice input is unavailable in this browser.";
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

    function releaseMediaStream() {
        if (mediaStream) {
            mediaStream.getTracks().forEach((track) => track.stop());
        }
        mediaStream = null;

        // iPad Safari can leave the audio route in a recording-oriented state
        // after getUserMedia(). Put it back into playback before the robot talks.
        if (isIOSLike()) {
            setTabletAudioSession("playback");
            window.__hriLastMicReleaseAt = Date.now();
            window.setTimeout(() => {
                try { window.speechSynthesis?.resume?.(); } catch (_) {}
            }, 80);
        }
    }

    function stopRecording(abort = false) {
        if (!mediaRecorder) {
            releaseMediaStream();
            return;
        }
        try {
            if (mediaRecorder.state !== "inactive") {
                if (abort) {
                    mediaRecorder.onstop = null;
                    mediaRecorder.stop();
                } else {
                    mediaRecorder.stop();
                }
            }
        } catch (error) {
            console.debug("MediaRecorder stop ignored:", error);
        }
        if (abort) {
            mediaRecorder = null;
            mediaChunks = [];
            releaseMediaStream();
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
        stopRecording(true);
        voiceInputMode = null;
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

    function handleRobotReply(data, transcriptText = "") {
        if (transcriptText) {
            setTranscript(`You: ${transcriptText}`);
        } else {
            setTranscript("");
        }

        if (typeof setIdleSpeech === "function") setIdleSpeech(data.text);
        if (typeof setFaceExpression === "function" && el("robot-face")) {
            setFaceExpression(el("robot-face"), data.expression || "happy");
        }
        if (typeof popEmoji === "function") popEmoji(data.emoji || "💬");

        setVoiceStatus("Speaking", "speaking");
        if (isIOSLike()) {
            setTabletAudioSession("playback");
        }
        if (typeof speak === "function") {
            speak(data.text, el("robot-face"), data.expression || "happy");
        }

        loadConversationHistory(false);

        const words = String(data.text || "").trim().split(/\s+/).filter(Boolean).length;
        const estimatedSpeechMs = Math.max(1800, Math.min(12000, words * 430));
        window.setTimeout(() => {
            if (!voiceSessionActive && !isThinking) {
                setTranscript("");
                setVoiceStatus(idlePrompt(), "idle");
            }
        }, estimatedSpeechMs);
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

        if (typeof setIdleSpeech === "function") setIdleSpeech("…");
        if (typeof setFaceExpression === "function" && el("robot-face")) {
            setFaceExpression(el("robot-face"), "attentive");
        }

        try {
            const data = await api("/api/chat", {
                method: "POST",
                body: JSON.stringify({ message: cleaned }),
            });
            handleRobotReply(data, cleaned);
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

    async function sendRecordedAudio(blob, mimeType) {
        if (!blob || blob.size === 0 || isThinking) {
            showVoiceError("I didn’t hear any audio. Tap and try again.");
            return;
        }

        isThinking = true;
        voiceSessionActive = false;
        setListeningVisual(false);
        setTranscript("");
        setVoiceStatus("Understanding you…", "transcribing");
        if (typeof setIdleSpeech === "function") setIdleSpeech("…");

        try {
            const form = new FormData();
            const ext = mimeType.includes("mp4") ? "m4a" :
                mimeType.includes("ogg") ? "ogg" :
                mimeType.includes("wav") ? "wav" : "webm";
            form.append("audio", blob, `robot-turn.${ext}`);
            form.append("mime_type", mimeType || blob.type || "audio/webm");

            const response = await fetch("/api/voice/chat", {
                method: "POST",
                body: form,
            });

            let data = {};
            try {
                data = await response.json();
            } catch (_) {
                data = {};
            }

            if (!response.ok) {
                throw new Error(data.error || `Voice request failed (${response.status}).`);
            }

            const transcript = String(data.transcript || "").trim();
            if (!transcript) throw new Error("No speech was detected in that recording.");

            handleRobotReply(data, transcript);
        } catch (error) {
            console.error("Recorded voice request failed:", error);
            if (typeof setIdleSpeech === "function") {
                setIdleSpeech("Sorry, I could not understand that just now.");
            }
            showVoiceError(error.message || "I could not understand that just now.");
        } finally {
            isThinking = false;
            mediaChunks = [];
            mediaRecorder = null;
            releaseMediaStream();
        }
    }

    function finaliseRecognitionSession() {
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
            restartTimer = window.setTimeout(() => {
                restartTimer = null;
                if (voiceSessionActive && !recognitionActive && !isThinking && !fatalRecognitionError) {
                    try {
                        recognition.start();
                    } catch (_) {
                        showVoiceError("The microphone is still busy. Please try again.");
                        voiceSessionActive = false;
                        setListeningVisual(false);
                    }
                }
            }, 250);
        }
    }

    function configureRecognition() {
        if (!SpeechRecognitionClass) return;

        recognition = new SpeechRecognitionClass();
        recognition.continuous = true;
        recognition.interimResults = true;
        recognition.maxAlternatives = 1;
        recognition.lang = /^en/i.test(navigator.language || "")
            ? navigator.language
            : "en-AU";

        recognition.onstart = () => {
            recognitionActive = true;
            if (voiceSessionActive && voiceInputMode === "recognition") {
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

                if (result.isFinal) newFinalText += `${newFinalText ? " " : ""}${text}`;
                else latestInterim = text;
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
                if (voiceSessionActive) setVoiceStatus(listeningPrompt(), "listening");
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
            if (code === "network" && recorderSupported()) {
                // Next tap can transparently use the server-side recorder path.
                recognition = null;
                voiceSessionActive = false;
                setListeningVisual(false);
                showVoiceError("Browser speech recognition failed. Tap again to use tablet recording.");
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
                finaliseRecognitionSession();
                return;
            }
            if (voiceSessionActive && voiceInputMode === "recognition" && !isThinking && !fatalRecognitionError) {
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

    function chooseRecordingMimeType() {
        if (!window.MediaRecorder) return "";
        const candidates = [
            "audio/mp4",
            "audio/webm;codecs=opus",
            "audio/webm",
            "audio/ogg;codecs=opus",
        ];
        return candidates.find((type) => {
            try {
                return MediaRecorder.isTypeSupported(type);
            } catch (_) {
                return false;
            }
        }) || "";
    }

    async function startRecordingSession() {
        if (!recorderSupported()) {
            if (!window.isSecureContext) {
                showVoiceError("Tablet microphone access needs HTTPS. Open the secure robot address.");
            } else {
                showVoiceError("Audio recording is unavailable in this browser.");
            }
            return;
        }

        try {
            if (isIOSLike()) {
                // Tell WebKit explicitly that this phase is microphone capture.
                // releaseMediaStream() switches it back to playback afterwards.
                setTabletAudioSession("play-and-record");
            }

            mediaStream = await navigator.mediaDevices.getUserMedia({
                audio: {
                    echoCancellation: true,
                    noiseSuppression: true,
                    autoGainControl: true,
                },
                video: false,
            });

            recordingMimeType = chooseRecordingMimeType();
            mediaChunks = [];
            mediaRecorder = recordingMimeType
                ? new MediaRecorder(mediaStream, { mimeType: recordingMimeType })
                : new MediaRecorder(mediaStream);
            recordingMimeType = mediaRecorder.mimeType || recordingMimeType || "audio/webm";

            mediaRecorder.ondataavailable = (event) => {
                if (event.data && event.data.size > 0) mediaChunks.push(event.data);
            };

            mediaRecorder.onerror = (event) => {
                console.error("MediaRecorder error:", event.error || event);
                voiceSessionActive = false;
                setListeningVisual(false);
                releaseMediaStream();
                showVoiceError("The tablet could not record audio. Check microphone permission.");
            };

            mediaRecorder.onstop = () => {
                const blob = new Blob(mediaChunks, { type: recordingMimeType || "audio/webm" });
                const finalMimeType = blob.type || recordingMimeType || "audio/webm";
                const durationMs = recordingStartedAt ? Date.now() - recordingStartedAt : 0;
                console.info("[V4.3.2] Recorded tablet audio", {
                    bytes: blob.size,
                    mimeType: finalMimeType,
                    durationMs,
                });
                mediaChunks = [];
                recordingStartedAt = 0;
                releaseMediaStream();

                if (blob.size < 1024) {
                    showVoiceError("The tablet recording was too small. Please tap, speak, then tap again.");
                    return;
                }
                sendRecordedAudio(blob, finalMimeType);
            };

            // Safari/iPad can produce broken or incomplete MP4 fragments with
            // short MediaRecorder timeslices. For a conversational turn we do not
            // need streaming chunks, so record one complete file and let stop()
            // emit the final dataavailable event. This is also fine on Android.
            recordingStartedAt = Date.now();
            mediaRecorder.start();
            setListeningVisual(true);
            setVoiceStatus(listeningPrompt(), "recording");
            if (typeof setIdleSpeech === "function") setIdleSpeech("I’m listening.");
        } catch (error) {
            voiceSessionActive = false;
            voiceInputMode = null;
            releaseMediaStream();
            setListeningVisual(false);
            if (error?.name === "NotAllowedError" || error?.name === "SecurityError") {
                showVoiceError("Microphone permission is blocked. Allow microphone access for this robot site.");
            } else {
                showVoiceError(error?.message || "The tablet microphone could not start.");
            }
        }
    }

    function startVoiceSession() {
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

        voiceInputMode = preferredInputMode();
        if (voiceInputMode === "recording") {
            startRecordingSession();
            return;
        }
        if (voiceInputMode === "recognition") {
            setListeningVisual(true);
            setVoiceStatus(listeningPrompt(), "listening");
            if (typeof setIdleSpeech === "function") setIdleSpeech("I’m listening.");
            startRecognitionEngine();
            return;
        }

        voiceSessionActive = false;
        if (!window.isSecureContext && (isIOSLike() || isAndroidLike())) {
            showVoiceError("Voice needs HTTPS on this tablet. Use the secure robot address.");
        } else {
            showVoiceError("Voice input is unavailable in this browser.");
        }
    }

    function finishVoiceSession() {
        if (!voiceSessionActive || isThinking) return;

        if (voiceInputMode === "recording") {
            voiceSessionActive = false;
            setVoiceStatus("Got it — processing your sentence…", "finishing");
            setListeningVisual(false);
            if (mediaRecorder && mediaRecorder.state !== "inactive") {
                mediaRecorder.stop();
            } else {
                releaseMediaStream();
                showVoiceError("The recording ended unexpectedly. Please try again.");
            }
            return;
        }

        voiceSessionActive = false;
        submitAfterRecognitionEnds = true;
        setVoiceStatus("Got it — finishing your sentence…", "finishing");
        stopRecognition(false);

        if (!recognitionActive) {
            window.setTimeout(finaliseRecognitionSession, 80);
            return;
        }

        finishFallbackTimer = window.setTimeout(() => {
            finaliseRecognitionSession();
        }, 1200);
    }

    function toggleVoiceSession() {
        if (voiceSessionActive) finishVoiceSession();
        else startVoiceSession();
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
            note.textContent = "The voice comes from this device/browser. Your choice is saved on this device.";
        }
    }

    function saveVoiceSelection() {
        const select = el("v4-voice-select");
        if (!select?.value) return;
        try {
            window.localStorage.setItem(VOICE_STORAGE_KEY, select.value);
        } catch (_) {}

        if (typeof refreshPreferredSpeechVoice === "function") refreshPreferredSpeechVoice();
        if (typeof showToast === "function") showToast(`Robot voice set to ${select.value}.`);
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
                    <p class="panel-note">Choose a text-to-speech voice exposed by this device/browser.</p>
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

        if (typeof setIdleSpeech === "function") setIdleSpeech("Tap my face and talk to me.");

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
        document.body.classList.add("v4-chat-replaced-by-voice");
    }

    function initialiseV4() {
        hideLegacyChatUI();
        installVoiceUI();
        installControlCentreExtras();
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", () => {
            window.setTimeout(initialiseV4, 700);
        }, { once: true });
    } else {
        window.setTimeout(initialiseV4, 700);
    }
})();
