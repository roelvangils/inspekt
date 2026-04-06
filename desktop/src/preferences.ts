import "./app.css";
import Preferences from "./lib/components/Preferences.svelte";
import { mount } from "svelte";
import { applyPlatformClass, loadPlatformStyles } from "./lib/utils/platform";
import { initI18n, type LocaleCode } from "$lib/i18n";

// Initialize platform-specific styling and i18n
async function init() {
  // Load platform styles
  await applyPlatformClass();
  await loadPlatformStyles();

  // Initialize i18n with saved language preference
  const savedLanguage = localStorage.getItem("inspekt-language") as LocaleCode | "system" | null;
  await initI18n(savedLanguage);
}

// Initialize before mounting app
init()
  .then(() => {
    mount(Preferences, {
      target: document.getElementById("app")!,
    });
  })
  .catch(console.error);
