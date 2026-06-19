import { state } from "./state.js";

// Onboarding module: handles first-time welcome state without duplicating
// existing feature wiring (file input click handlers live in events.js).
export function initOnboarding(options = {}) {
  const welcomeSel = options.welcomeSelector || "#welcomeOverlay";
  const fileInputSel = options.fileInputSelector || "#fileInput";
  const welcomeOverlay = document.querySelector(welcomeSel);
  const fileInput = document.querySelector(fileInputSel);

  function enterFirstMode() {
    document.body.classList.add("welcome-first-mode");
    if (welcomeOverlay) {
      welcomeOverlay.classList.remove("hidden");
      welcomeOverlay.style.display = "flex";
      welcomeOverlay.style.visibility = "visible";
      welcomeOverlay.style.opacity = 1;
    }
  }

  function exitFirstMode() {
    document.body.classList.remove("welcome-first-mode");
    if (welcomeOverlay) {
      welcomeOverlay.classList.add("hidden");
      welcomeOverlay.style.display = "none";
    }
  }

  // Activate onboarding if no original image is present
  if (!state.originalImage && welcomeOverlay) enterFirstMode();

  // Listen to the central file input change event (events.js also listens)
  if (fileInput) {
    fileInput.addEventListener("change", (e) => {
      if (e.target.files && e.target.files.length) {
        // allow other listeners (handleImageUpload) to run first
        setTimeout(() => exitFirstMode(), 60);
      }
    });
  }

  // Fallback: watch state if some module sets originalImage programmatically
  const iv = setInterval(() => {
    if (state.originalImage) {
      exitFirstMode();
      clearInterval(iv);
    }
  }, 200);

  return { enterFirstMode, exitFirstMode };
}
