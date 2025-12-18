"""
Shared Chrome-style dialog styles.

Used by both recording (record_events.js) and replay (replay_visual.js).
This ensures visual consistency between synthetic dialogs shown during
recording and replay modes.

Class names:
- .inspekt-dialog-backdrop - Full-screen semi-transparent overlay
- .inspekt-dialog - The dialog container
- .inspekt-dialog-heading - "{domain} says" heading
- .inspekt-dialog-message - The dialog message
- .inspekt-dialog-input - Text input for prompt dialogs
- .inspekt-dialog-buttons - Button container
- .inspekt-dialog-btn - Base button class
- .inspekt-dialog-btn-primary - OK button (blue)
- .inspekt-dialog-btn-secondary - Cancel button (light blue)
- .inspekt-dialog-note - Small explanatory note (used in recording mode)
"""

DIALOG_STYLES = """
.inspekt-dialog-backdrop {
  all: unset;
  display: block !important;
  position: fixed !important;
  top: 0 !important;
  left: 0 !important;
  width: 100vw !important;
  height: 100vh !important;
  background: rgba(0, 0, 0, 0.6) !important;
  z-index: 2147483646 !important;
}
.inspekt-dialog-backdrop.inspekt-fade-in {
  animation: inspektDialogFadeIn 0.1s ease-out;
}
.inspekt-dialog-backdrop.inspekt-fade-out {
  animation: inspektDialogFadeOut 0.1s ease-in forwards;
}
.inspekt-dialog {
  all: unset;
  display: block !important;
  position: fixed !important;
  top: 8px !important;
  left: 50% !important;
  transform: translateX(-50%) !important;
  width: 480px !important;
  padding: 20px !important;
  border-radius: 12px;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  z-index: 2147483647 !important;
  box-sizing: border-box;
  /* Light mode (default) */
  --dialog-bg: #ffffff;
  --dialog-text: #000000;
  --dialog-shadow: 0 2px 10px rgba(0, 0, 0, 0.1);
  --btn-primary-bg: #2656c9;
  --btn-primary-hover: #3c67ce;
  --btn-secondary-bg: #d6e1fb;
  --btn-secondary-hover: #cbd7ee;
  --input-border: #ccc;
  --input-bg: #ffffff;
  background: var(--dialog-bg);
  color: var(--dialog-text);
  box-shadow: var(--dialog-shadow);
}
.inspekt-dialog.inspekt-fade-in {
  animation: inspektDialogFadeIn 0.1s ease-out;
}
.inspekt-dialog.inspekt-fade-out {
  animation: inspektDialogFadeOut 0.1s ease-in forwards;
}
@media (prefers-color-scheme: dark) {
  .inspekt-dialog {
    --dialog-bg: #1f1f1f;
    --dialog-text: #ffffff;
    --dialog-shadow: 0 2px 10px rgba(0, 0, 0, 0.3);
    --input-border: #555;
    --input-bg: #2a2a2a;
  }
}
@keyframes inspektDialogFadeIn {
  from { opacity: 0; }
  to { opacity: 1; }
}
@keyframes inspektDialogFadeOut {
  from { opacity: 1; }
  to { opacity: 0; }
}
.inspekt-dialog-heading {
  all: unset;
  display: block;
  font-size: 16px;
  font-weight: bold;
  margin-bottom: 8px;
  color: var(--dialog-text);
}
.inspekt-dialog-message {
  all: unset;
  display: block;
  font-size: 14px;
  line-height: 1.4;
  margin-bottom: 16px;
  word-break: break-word;
  color: var(--dialog-text);
}
.inspekt-dialog-input {
  all: unset;
  display: block;
  width: 100%;
  height: 35px;
  padding: 0 10px;
  margin-bottom: 16px;
  border: 2px solid var(--input-border);
  border-radius: 5px;
  background: var(--input-bg);
  color: var(--dialog-text);
  font-size: 14px;
  font-family: inherit;
  box-sizing: border-box;
}
.inspekt-dialog-input:focus {
  border-color: var(--btn-primary-bg);
  outline: none;
}
.inspekt-dialog-buttons {
  all: unset;
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}
.inspekt-dialog-btn {
  all: unset;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 8px 20px;
  border-radius: 20px;
  font-size: 14px;
  font-weight: 500;
  font-family: inherit;
  cursor: pointer;
}
.inspekt-dialog-btn:focus {
  outline: 2px solid var(--btn-primary-bg);
  outline-offset: 2px;
}
.inspekt-dialog-btn-primary {
  background: var(--btn-primary-bg);
  color: #ffffff;
}
.inspekt-dialog-btn-primary:hover {
  background: var(--btn-primary-hover);
}
.inspekt-dialog-btn-secondary {
  background: var(--btn-secondary-bg);
  color: #000000;
}
.inspekt-dialog-btn-secondary:hover {
  background: var(--btn-secondary-hover);
}
.inspekt-dialog-note {
  all: unset;
  display: block;
  font-size: 11px;
  line-height: 1.4;
  margin-top: 12px;
  color: #888888;
  text-align: center;
}
@media (prefers-color-scheme: dark) {
  .inspekt-dialog-note {
    color: #666666;
  }
}
""".strip()
