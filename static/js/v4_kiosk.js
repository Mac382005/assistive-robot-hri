/* HRI Robot V4.4.1 - commercial display / kiosk layer */
(() => {
    "use strict";

    const STORAGE_KEY = "hri_robot_display_preference";
    let wakeLock = null;

    const el = (id) => document.getElementById(id);

    function isInstalledDisplayMode() {
        return window.matchMedia?.("(display-mode: fullscreen)").matches
            || window.matchMedia?.("(display-mode: standalone)").matches
            || window.navigator.standalone === true;
    }

    function isFullscreen() {
        return Boolean(document.fullscreenElement || document.webkitFullscreenElement);
    }

    function canRequestFullscreen() {
        const root = document.documentElement;
        return Boolean(root.requestFullscreen || root.webkitRequestFullscreen);
    }

    function displayModeLabel() {
        if (window.matchMedia?.("(display-mode: fullscreen)").matches) return "Installed fullscreen app";
        if (window.matchMedia?.("(display-mode: standalone)").matches || window.navigator.standalone === true) {
            return "Installed standalone app";
        }
        if (isFullscreen()) return "Browser fullscreen";
        return "Normal browser";
    }

    async function requestWakeLock() {
        if (!navigator.wakeLock?.request) return;
        try {
            wakeLock = await navigator.wakeLock.request("screen");
            wakeLock.addEventListener?.("release", () => { wakeLock = null; });
        } catch (error) {
            console.debug("Screen wake lock unavailable:", error);
        }
    }

    async function releaseWakeLock() {
        try {
            await wakeLock?.release?.();
        } catch (_) {
            // no-op
        }
        wakeLock = null;
    }

    async function enterFullscreen() {
        const root = document.documentElement;
        try {
            if (root.requestFullscreen) {
                try {
                    await root.requestFullscreen({ navigationUI: "hide" });
                } catch (_) {
                    await root.requestFullscreen();
                }
            } else if (root.webkitRequestFullscreen) {
                root.webkitRequestFullscreen();
            }
        } catch (error) {
            console.debug("Fullscreen request unavailable/denied:", error);
        }
    }

    async function exitFullscreen() {
        try {
            if (document.exitFullscreen && document.fullscreenElement) {
                await document.exitFullscreen();
            } else if (document.webkitExitFullscreen && document.webkitFullscreenElement) {
                document.webkitExitFullscreen();
            }
        } catch (error) {
            console.debug("Fullscreen exit ignored:", error);
        }
    }

    function setDisplayActive(active) {
        document.documentElement.classList.toggle("robot-display-active", active);
        document.body.classList.toggle("robot-display-active", active);
        updateDisplayStatus();
    }

    function launchOverlay() {
        return el("robot-launch-overlay");
    }

    function hideLaunchOverlay() {
        launchOverlay()?.classList.add("hidden");
    }

    function showLaunchOverlay() {
        launchOverlay()?.classList.remove("hidden");
    }

    async function startRobotMode() {
        // Prime iPad speech synthesis while this function still has direct user
        // activation. The promise is intentionally not awaited so fullscreen
        // permission remains tied to the same Start Robot tap.
        try { window.hriPrimeSpeechOutput?.(); } catch (_) {}

        // Must be initiated directly by a user click so iPad/desktop browsers are
        // allowed to enter Fullscreen API mode.
        setDisplayActive(true);
        hideLaunchOverlay();
        await requestWakeLock();

        if (!isInstalledDisplayMode() && !isFullscreen() && canRequestFullscreen()) {
            await enterFullscreen();
        }

        try { sessionStorage.setItem(STORAGE_KEY, "robot"); } catch (_) {}
        updateDisplayStatus();
    }

    async function leaveRobotMode() {
        await exitFullscreen();
        await releaseWakeLock();
        setDisplayActive(false);
        try { sessionStorage.setItem(STORAGE_KEY, "browser"); } catch (_) {}

        // Installed Home Screen web apps cannot be programmatically converted
        // back into a Safari tab. Keep the UI usable and tell the user how to
        // return to normal browsing.
        if (isInstalledDisplayMode()) {
            if (typeof showToast === "function") {
                showToast("Robot app mode closed. Swipe up/Home to leave the app; open the same address in Safari for normal browser mode.");
            }
        } else {
            showLaunchOverlay();
        }
        updateDisplayStatus();
    }

    function continueBrowserMode() {
        // This button is also a direct user gesture, so use it to unlock TTS.
        try { window.hriPrimeSpeechOutput?.(); } catch (_) {}
        setDisplayActive(false);
        hideLaunchOverlay();
        try { sessionStorage.setItem(STORAGE_KEY, "browser"); } catch (_) {}
        updateDisplayStatus();
    }

    function updateDisplayStatus() {
        const status = el("robot-display-status-text");
        if (status) status.textContent = displayModeLabel();

        const enter = el("robot-enter-fullscreen");
        const exit = el("robot-exit-fullscreen");
        if (enter) enter.hidden = isFullscreen() || isInstalledDisplayMode();
        if (exit) exit.hidden = !(isFullscreen() || isInstalledDisplayMode() || document.body.classList.contains("robot-display-active"));
    }

    function installLaunchScreen() {
        if (el("robot-launch-overlay")) return;

        const overlay = document.createElement("div");
        overlay.id = "robot-launch-overlay";
        overlay.className = "robot-launch-overlay";
        overlay.innerHTML = `
            <div class="robot-launch-card" role="dialog" aria-modal="true" aria-labelledby="robot-launch-title">
                <div class="robot-launch-mark" aria-hidden="true"><div class="robot-launch-face">⌒‿⌒</div></div>
                <h1 id="robot-launch-title">HRI Robot</h1>
                <p>Start the companion interface in distraction-free robot mode.</p>
                <div class="robot-launch-actions">
                    <button id="robot-launch-start" class="robot-launch-primary" type="button">Start Robot</button>
                    <button id="robot-launch-browser" class="robot-launch-secondary" type="button">Continue in browser</button>
                </div>
                <p class="robot-launch-tip">For the cleanest iPad experience: Safari → Share → Add to Home Screen → Open as Web App.</p>
            </div>
        `;
        document.body.appendChild(overlay);

        el("robot-launch-start")?.addEventListener("click", startRobotMode);
        el("robot-launch-browser")?.addEventListener("click", continueBrowserMode);
    }

    function installExitChip() {
        if (el("robot-display-exit-chip")) return;
        const button = document.createElement("button");
        button.id = "robot-display-exit-chip";
        button.className = "robot-display-exit-chip";
        button.type = "button";
        button.title = "Exit robot display mode";
        button.setAttribute("aria-label", "Exit robot display mode");
        button.textContent = "×";
        button.addEventListener("click", leaveRobotMode);
        document.body.appendChild(button);
    }

    function installControlCentreSection() {
        if (el("robot-display-settings")) return;
        const panel = el("developer-panel");
        if (!panel) return;

        const section = document.createElement("section");
        section.id = "robot-display-settings";
        section.className = "panel-section robot-display-section";
        section.innerHTML = `
            <div class="section-heading-row">
                <div>
                    <h3>Robot display mode</h3>
                    <p class="panel-note">Use fullscreen for demonstrations, or install this HTTPS page on the iPad Home Screen for an app-like display with no Safari address bar.</p>
                </div>
                <span class="robot-display-status"><span aria-hidden="true">●</span><span id="robot-display-status-text">${displayModeLabel()}</span></span>
            </div>
            <div class="robot-display-actions">
                <button id="robot-enter-fullscreen" class="secondary-button" type="button">Enter full screen</button>
                <button id="robot-exit-fullscreen" class="secondary-button" type="button">Exit robot mode</button>
            </div>
            <p class="panel-note">iPad: Safari → Share → Add to Home Screen → keep “Open as Web App” enabled. Launching that icon gives the most commercial-looking presentation.</p>
        `;

        const firstSection = panel.querySelector(".panel-section");
        panel.insertBefore(section, firstSection || null);

        el("robot-enter-fullscreen")?.addEventListener("click", startRobotMode);
        el("robot-exit-fullscreen")?.addEventListener("click", leaveRobotMode);
        updateDisplayStatus();
    }

    function initialise() {
        installLaunchScreen();
        installExitChip();
        installControlCentreSection();

        const installed = isInstalledDisplayMode();
        const params = new URLSearchParams(window.location.search);
        const explicitRobot = params.get("robot") === "1";

        if (installed || explicitRobot) {
            setDisplayActive(true);
            hideLaunchOverlay();
            requestWakeLock();
        } else {
            let preference = "";
            try { preference = sessionStorage.getItem(STORAGE_KEY) || ""; } catch (_) {}
            if (preference === "browser") continueBrowserMode();
            else showLaunchOverlay();
        }

        document.addEventListener("fullscreenchange", () => {
            if (!isFullscreen() && !isInstalledDisplayMode()) {
                // ESC / browser control exits fullscreen but leaves the webpage
                // usable instead of immediately forcing the user back in.
                setDisplayActive(false);
            }
            updateDisplayStatus();
        });
        document.addEventListener("webkitfullscreenchange", updateDisplayStatus);

        document.addEventListener("visibilitychange", () => {
            if (document.visibilityState === "visible" && document.body.classList.contains("robot-display-active")) {
                requestWakeLock();
            }
        });
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", () => window.setTimeout(initialise, 850), { once: true });
    } else {
        window.setTimeout(initialise, 850);
    }
})();
