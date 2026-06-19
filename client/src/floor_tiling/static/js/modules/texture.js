import { state } from "./state.js";
import { updateTilePreview } from "./ui.js";
import { saveTilePreferences } from "./persistence.js";

// Texture upload and handling (to be filled in next steps)
// This will handle texture uploads and previews

export function initTextureUpload() {
  _bindTextureSlot(
    document.getElementById("textureUploadArea"),
    document.getElementById("textureFileInput"),
    "light",
  );
  _bindTextureSlot(
    document.getElementById("textureDarkUploadArea"),
    document.getElementById("textureDarkFileInput"),
    "dark",
  );
  _bindTextureSlot(
    document.getElementById("paintTextureUploadArea"),
    document.getElementById("paintTextureFileInput"),
    "paint",
  );
}

function _bindTextureSlot(area, input, which) {
  area.addEventListener("click", () => input.click());
  area.addEventListener("dragover", (e) => {
    e.preventDefault();
    area.style.borderColor = "#667eea";
  });
  area.addEventListener("dragleave", () => {
    area.style.borderColor = "";
  });
  area.addEventListener("drop", (e) => {
    e.preventDefault();
    area.style.borderColor = "";
    const f = e.dataTransfer.files[0];
    if (f && f.type.startsWith("image/")) loadTextureFile(f, which);
  });
  input.addEventListener("change", (e) => {
    if (e.target.files[0]) loadTextureFile(e.target.files[0], which);
  });
}

function loadTextureFile(file, which = "light") {
  const reader = new FileReader();
  reader.onload = (e) => {
    if (which === "paint") {
      state.paintTextureDataUrl = e.target.result;
      document.getElementById("paintTextureThumb").src = e.target.result;
      document.getElementById("paintTextureEmpty").style.display = "none";
      document.getElementById("paintTexturePreview").style.display = "block";
      document
        .getElementById("paintTextureUploadArea")
        .classList.add("has-texture");
      const nameEl = document.getElementById("paintTextureName");
      if (nameEl) nameEl.textContent = file.name;
      saveTilePreferences();
      document.dispatchEvent(new Event("liveapply"));
      return;
    }
    if (which === "dark") {
      state.tileTextureDarkDataUrl = e.target.result;
      document.getElementById("textureDarkThumb").src = e.target.result;
      document.getElementById("textureDarkEmpty").style.display = "none";
      document.getElementById("textureDarkPreview").style.display = "block";
      document
        .getElementById("textureDarkUploadArea")
        .classList.add("has-texture");
      const nameEl = document.getElementById("textureDarkName");
      if (nameEl) nameEl.textContent = file.name;
    } else {
      state.tileTextureDataUrl = e.target.result;
      document.getElementById("textureThumb").src = e.target.result;
      document.getElementById("textureEmpty").style.display = "none";
      document.getElementById("texturePreview").style.display = "block";
      document.getElementById("textureUploadArea").classList.add("has-texture");
      const nameEl = document.getElementById("textureName");
      if (nameEl) nameEl.textContent = file.name;
    }
    updateTilePreview();
    // Save preferences after texture upload
    saveTilePreferences();
    document.dispatchEvent(new Event("liveapply"));
  };
  reader.readAsDataURL(file);
}
