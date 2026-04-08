import "./app.css";
import Preferences from "./lib/components/Preferences.svelte";
import { mount } from "svelte";

mount(Preferences, {
  target: document.getElementById("app")!,
});
