pub mod menu;

use serde::{Deserialize, Serialize};
use std::time::Duration;
use tauri::{Emitter, Listener, Manager, WebviewUrl, WebviewWindowBuilder};
use tauri_plugin_clipboard_manager::ClipboardExt;

#[cfg(target_os = "macos")]
use window_vibrancy::{apply_vibrancy, NSVisualEffectMaterial};

#[cfg(target_os = "macos")]
use objc2_app_kit::{NSColor, NSColorSpace, NSWorkspace};

const CONTROL_SERVER: &str = "http://localhost:8888";

// ── macOS Accessibility & Accent Color ─────────────────────────────

#[derive(Serialize, Deserialize, Debug, Clone, Default)]
#[serde(rename_all = "camelCase")]
pub struct AccessibilitySettings {
    pub reduce_transparency: bool,
    pub increase_contrast: bool,
    pub reduce_motion: bool,
    pub differentiate_without_color: bool,
    pub invert_colors: bool,
    pub accent_color: String,
}

#[cfg(target_os = "macos")]
fn get_accent_color_hex() -> String {
    let accent_color = NSColor::controlAccentColor();
    let color_space = NSColorSpace::sRGBColorSpace();
    if let Some(rgb_color) = accent_color.colorUsingColorSpace(&color_space) {
        let r = (rgb_color.redComponent() * 255.0).round() as u8;
        let g = (rgb_color.greenComponent() * 255.0).round() as u8;
        let b = (rgb_color.blueComponent() * 255.0).round() as u8;
        format!("#{:02X}{:02X}{:02X}", r, g, b)
    } else {
        "#007AFF".to_string()
    }
}

#[cfg(target_os = "macos")]
fn get_accessibility_settings_internal() -> AccessibilitySettings {
    let workspace = NSWorkspace::sharedWorkspace();
    AccessibilitySettings {
        reduce_transparency: workspace.accessibilityDisplayShouldReduceTransparency(),
        increase_contrast: workspace.accessibilityDisplayShouldIncreaseContrast(),
        reduce_motion: workspace.accessibilityDisplayShouldReduceMotion(),
        differentiate_without_color: workspace.accessibilityDisplayShouldDifferentiateWithoutColor(),
        invert_colors: workspace.accessibilityDisplayShouldInvertColors(),
        accent_color: get_accent_color_hex(),
    }
}

#[cfg(target_os = "macos")]
#[tauri::command]
fn get_system_accent_color() -> String {
    get_accent_color_hex()
}

#[cfg(not(target_os = "macos"))]
#[tauri::command]
fn get_system_accent_color() -> String {
    "#007AFF".to_string()
}

#[cfg(target_os = "macos")]
#[tauri::command]
fn get_accessibility_settings() -> AccessibilitySettings {
    get_accessibility_settings_internal()
}

#[cfg(not(target_os = "macos"))]
#[tauri::command]
fn get_accessibility_settings() -> AccessibilitySettings {
    AccessibilitySettings::default()
}

#[tauri::command]
fn start_dragging(window: tauri::WebviewWindow) -> Result<(), String> {
    window.start_dragging().map_err(|e| e.to_string())
}


#[tauri::command]
async fn resize_preferences_window(app: tauri::AppHandle, height: f64) -> Result<(), String> {
    if let Some(window) = app.get_webview_window("preferences") {
        window
            .set_size(tauri::Size::Logical(tauri::LogicalSize {
                width: 500.0,
                height,
            }))
            .map_err(|e| e.to_string())?;
    }
    Ok(())
}

fn open_preferences_window(app: &tauri::AppHandle) -> Result<(), tauri::Error> {
    if let Some(window) = app.get_webview_window("preferences") {
        window.set_focus()?;
        return Ok(());
    }

    let preferences_window = WebviewWindowBuilder::new(
        app,
        "preferences",
        WebviewUrl::App("preferences.html".into()),
    )
    .title("General")
    .inner_size(500.0, 400.0)
    .resizable(false)
    .center()
    .focused(true)
    .visible(true)
    .transparent(true)
    .title_bar_style(tauri::TitleBarStyle::Overlay)
    .hidden_title(true)
    .build()?;

    #[cfg(target_os = "macos")]
    {
        let settings = get_accessibility_settings_internal();
        if !settings.reduce_transparency {
            let _ = apply_vibrancy(
                &preferences_window,
                NSVisualEffectMaterial::UnderWindowBackground,
                None,
                None,
            );
        }
    }

    Ok(())
}

// ── VM Management ──────────────────────────────────────────────────

/// VM status information returned to the frontend.
#[derive(Serialize, Clone, Debug)]
#[serde(rename_all = "camelCase")]
pub struct VmStatus {
    pub docker_running: bool,
    pub container_running: bool,
    pub health_ok: bool,
}

/// Check whether Docker is available and running.
#[tauri::command]
async fn check_docker() -> Result<bool, String> {
    let output = tokio::process::Command::new("docker")
        .arg("info")
        .stdout(std::process::Stdio::null())
        .stderr(std::process::Stdio::null())
        .status()
        .await
        .map_err(|e| format!("Failed to run docker: {}", e))?;

    Ok(output.success())
}

/// Get the current VM status: is Docker running, is the container running, is it healthy?
#[tauri::command]
async fn check_vm_status() -> Result<VmStatus, String> {
    // Check Docker
    let docker_ok = check_docker().await.unwrap_or(false);
    if !docker_ok {
        return Ok(VmStatus {
            docker_running: false,
            container_running: false,
            health_ok: false,
        });
    }

    // Check container
    let container_output = tokio::process::Command::new("docker")
        .args(["ps", "-q", "-f", "name=inspekt-browser-vm"])
        .output()
        .await
        .map_err(|e| format!("Failed to check container: {}", e))?;

    let container_running = !String::from_utf8_lossy(&container_output.stdout)
        .trim()
        .is_empty();

    if !container_running {
        return Ok(VmStatus {
            docker_running: true,
            container_running: false,
            health_ok: false,
        });
    }

    // Check health
    let health_ok = check_health_once().await;

    Ok(VmStatus {
        docker_running: true,
        container_running: true,
        health_ok,
    })
}

/// Start the VM, emitting progress events to the frontend.
#[tauri::command]
async fn start_vm(app: tauri::AppHandle) -> Result<(), String> {
    let _ = app.emit("vm-progress", "Checking Docker…");

    let docker_ok = check_docker().await.unwrap_or(false);
    if !docker_ok {
        let _ = app.emit("vm-error", "Docker is not running");
        return Err("Docker is not running".to_string());
    }

    // Check if already running
    let status = check_vm_status().await?;
    if status.container_running && status.health_ok {
        let _ = app.emit("vm-ready", "http://localhost:6080/control.html");
        return Ok(());
    }

    let _ = app.emit("vm-progress", "Starting VM…");

    // Shell out to `inspekt vm start --no-open` which handles all Docker logic
    let output = tokio::process::Command::new("inspekt")
        .args(["vm", "start", "--no-open"])
        .stdout(std::process::Stdio::piped())
        .stderr(std::process::Stdio::piped())
        .output()
        .await
        .map_err(|e| {
            let msg = format!("Failed to run inspekt: {}. Is the inspekt CLI installed?", e);
            let _ = app.emit("vm-error", &msg);
            msg
        })?;

    if !output.status.success() {
        let stderr = String::from_utf8_lossy(&output.stderr);
        let stdout = String::from_utf8_lossy(&output.stdout);
        let detail = if !stderr.is_empty() {
            stderr.trim().to_string()
        } else if !stdout.is_empty() {
            stdout.trim().to_string()
        } else {
            "inspekt vm start failed (no output)".to_string()
        };
        let _ = app.emit("vm-error", &detail);
        return Err(detail);
    }

    // Poll health endpoint until ready
    let _ = app.emit("vm-progress", "Waiting for VM to become ready…");

    for i in 0..60 {
        if check_health_once().await {
            let _ = app.emit("vm-ready", "http://localhost:6080/control.html");
            return Ok(());
        }
        let _ = app.emit(
            "vm-progress",
            format!("Waiting for VM to become ready... ({}/60)", i + 1),
        );
        tokio::time::sleep(Duration::from_secs(1)).await;
    }

    let msg = "VM failed to become healthy after 60 seconds".to_string();
    let _ = app.emit("vm-error", &msg);
    Err(msg)
}

/// Stop the VM.
#[tauri::command]
async fn stop_vm(app: tauri::AppHandle) -> Result<(), String> {
    let _ = app.emit("vm-progress", "Stopping VM…");

    let output = tokio::process::Command::new("inspekt")
        .args(["vm", "stop"])
        .stdout(std::process::Stdio::piped())
        .stderr(std::process::Stdio::piped())
        .status()
        .await
        .map_err(|e| format!("Failed to stop VM: {}", e))?;

    if output.success() {
        let _ = app.emit("vm-stopped", ());
        Ok(())
    } else {
        Err("Failed to stop VM".to_string())
    }
}

/// Open the VM window showing the control panel at localhost:6080.
#[tauri::command]
async fn open_vm_window(app: tauri::AppHandle) -> Result<(), String> {
    // If the window already exists, just focus it
    if let Some(window) = app.get_webview_window("vm") {
        window.set_focus().map_err(|e| e.to_string())?;
        return Ok(());
    }

    let url: url::Url = "http://localhost:6080/control.html"
        .parse()
        .map_err(|e: url::ParseError| e.to_string())?;

    let _vm_window = WebviewWindowBuilder::new(&app, "vm", WebviewUrl::External(url))
        .title("Inspekt Browser VM")
        .inner_size(1440.0, 900.0)
        .min_inner_size(1024.0, 700.0)
        .center()
        .focused(true)
        .title_bar_style(tauri::TitleBarStyle::Overlay)
        .hidden_title(true)
        .traffic_light_position(tauri::Position::Logical(tauri::LogicalPosition::new(16.0, 18.0)))
        .build()
        .map_err(|e| format!("Failed to create VM window: {}", e))?;

    // Hide the launcher window
    if let Some(main_window) = app.get_webview_window("main") {
        let _ = main_window.hide();
    }

    Ok(())
}

/// Open a new VM window focused on a specific tab.
/// Used for tab tear-off: dragging a tab out of the tab bar creates a new window.
#[tauri::command]
async fn open_tab_window(
    app: tauri::AppHandle,
    _tab_url: String,
    title: String,
    focus_tab_id: String,
) -> Result<(), String> {
    let label = format!("vm-{}", std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .unwrap_or_default()
        .as_millis());

    let url: url::Url = format!(
        "http://localhost:6080/control.html?focus={}",
        urlencoding::encode(&focus_tab_id)
    )
        .parse()
        .map_err(|e: url::ParseError| e.to_string())?;

    let window_title = if title.is_empty() {
        "Inspekt Browser VM".to_string()
    } else {
        format!("{title} — Inspekt Browser VM")
    };

    let _tab_window = WebviewWindowBuilder::new(&app, &label, WebviewUrl::External(url))
        .title(&window_title)
        .inner_size(1440.0, 900.0)
        .min_inner_size(1024.0, 700.0)
        .center()
        .focused(true)
        .title_bar_style(tauri::TitleBarStyle::Overlay)
        .hidden_title(true)
        .traffic_light_position(tauri::Position::Logical(tauri::LogicalPosition::new(16.0, 18.0)))
        .build()
        .map_err(|e| format!("Failed to create tab window: {}", e))?;

    Ok(())
}

/// Single health check attempt against the control server.
async fn check_health_once() -> bool {
    let client = reqwest::Client::builder()
        .timeout(Duration::from_secs(2))
        .build();

    let Ok(client) = client else {
        return false;
    };

    match client.get("http://localhost:8888/health").send().await {
        Ok(resp) => resp.status().is_success(),
        Err(_) => false,
    }
}

// ── Helper functions for menu actions ────────────────────────────────

/// Make a GET request to the control server.
async fn api_get(path: &str) -> Result<(), String> {
    let url = format!("{CONTROL_SERVER}{path}");
    reqwest::get(&url)
        .await
        .map_err(|e| format!("API request failed: {e}"))?;
    Ok(())
}

/// Make a POST request to the control server with an optional JSON body.
async fn api_post(path: &str, body: Option<serde_json::Value>) -> Result<(), String> {
    let url = format!("{CONTROL_SERVER}{path}");
    let client = reqwest::Client::new();
    let mut req = client.post(&url);
    if let Some(json) = body {
        req = req.json(&json);
    }
    req.send()
        .await
        .map_err(|e| format!("API request failed: {e}"))?;
    Ok(())
}

/// Run an inspekt CLI command asynchronously.
async fn run_inspekt(args: &[&str]) -> Result<(), String> {
    let output = tokio::process::Command::new("inspekt")
        .args(args)
        .stdout(std::process::Stdio::piped())
        .stderr(std::process::Stdio::piped())
        .status()
        .await
        .map_err(|e| format!("Failed to run inspekt: {e}"))?;

    if !output.success() {
        return Err(format!("inspekt {} failed", args.join(" ")));
    }
    Ok(())
}

/// Fetch text from the control server's inspekt endpoint and copy it
/// to the system clipboard via the Tauri clipboard plugin.
/// Returns the text that was copied, or an error message.
async fn copy_inspekt_output(
    app: tauri::AppHandle,
    command: &str,
) -> Result<String, String> {
    let url = format!(
        "{CONTROL_SERVER}/inspekt/{}",
        urlencoding::encode(command)
    );
    let resp = reqwest::get(&url)
        .await
        .map_err(|e| format!("Request failed: {e}"))?;
    let data: serde_json::Value = resp
        .json()
        .await
        .map_err(|e| format!("JSON parse failed: {e}"))?;

    if data.get("ok").and_then(|v| v.as_bool()) != Some(true) {
        let err = data
            .get("error")
            .and_then(|v| v.as_str())
            .unwrap_or("No selection found");
        return Err(err.to_string());
    }

    let text = data
        .get("output")
        .and_then(|v| v.as_str())
        .unwrap_or("")
        .trim()
        .to_string();

    if text.is_empty() {
        return Err("No text to copy".to_string());
    }

    // Write to system clipboard via the Tauri clipboard plugin (Rust side)
    app.clipboard()
        .write_text(&text)
        .map_err(|e| format!("Clipboard write failed: {e}"))?;

    Ok(text)
}

/// Show a toast in the VM webview.
fn show_vm_toast(app: &tauri::AppHandle, message: &str, toast_type: &str) {
    if let Some(window) = app.get_webview_window("vm") {
        let escaped_msg = message.replace('\'', "\\'").replace('\n', "\\n");
        let _ = window.eval(&format!(
            "typeof showToast === 'function' && showToast('{escaped_msg}', '{toast_type}')"
        ));
    }
}

/// Copy inspekt output to clipboard and show a toast in the VM webview.
async fn copy_inspekt_with_toast(app: tauri::AppHandle, command: &str, label: &str) {
    show_vm_toast(&app, &format!("Copying {label}…"), "");
    match copy_inspekt_output(app.clone(), command).await {
        Ok(_) => show_vm_toast(&app, &format!("{label} copied!"), "success"),
        Err(e) => show_vm_toast(&app, &e, "error"),
    }
}

/// Poll the control server's clipboard-relay endpoint and copy to system clipboard.
/// The JS side POSTs text to /clipboard-relay, then this function reads it.
async fn poll_clipboard_relay(app: tauri::AppHandle) {
    let url = format!("{CONTROL_SERVER}/clipboard-relay");
    let resp = match reqwest::get(&url).await {
        Ok(r) => r,
        Err(_) => return,
    };
    let data: serde_json::Value = match resp.json().await {
        Ok(d) => d,
        Err(_) => return,
    };
    if data.get("ok").and_then(|v| v.as_bool()) == Some(true) {
        if let Some(text) = data.get("text").and_then(|v| v.as_str()) {
            if !text.is_empty() {
                let _ = app.clipboard().write_text(text);
                let label = data
                    .get("label")
                    .and_then(|v| v.as_str())
                    .unwrap_or("Text");
                show_vm_toast(&app, &format!("{label} copied!"), "success");
            }
        }
    }
}

/// Emit an event to the VM webview window.
fn emit_to_vm(app: &tauri::AppHandle, event: &str) {
    if let Some(window) = app.get_webview_window("vm") {
        let _ = window.eval(&format!(
            "window.dispatchEvent(new CustomEvent('tauri-menu', {{ detail: {{ action: '{event}' }} }}))"
        ));
    }
}

/// Emit an event to the VM webview window with a string payload.
fn emit_to_vm_with_payload(app: &tauri::AppHandle, event: &str, payload: &str) {
    if let Some(window) = app.get_webview_window("vm") {
        let _ = window.eval(&format!(
            "window.dispatchEvent(new CustomEvent('tauri-menu', {{ detail: {{ action: '{event}', value: '{payload}' }} }}))"
        ));
    }
}

/// Download a screenshot from the control server and save via native dialog.
async fn save_screenshot(app: tauri::AppHandle, endpoint: &str) -> Result<(), String> {
    let url = format!("{CONTROL_SERVER}{endpoint}");
    let resp = reqwest::get(&url)
        .await
        .map_err(|e| format!("Screenshot request failed: {e}"))?;

    let bytes = resp
        .bytes()
        .await
        .map_err(|e| format!("Failed to read screenshot: {e}"))?;

    save_bytes_file(&app, &bytes, "screenshot.png").await
}

/// Save raw bytes to a file via the native save dialog.
async fn save_bytes_file(
    _app: &tauri::AppHandle,
    bytes: &[u8],
    default_name: &str,
) -> Result<(), String> {
    // Use rfd (raw file dialog) for native save dialog
    let path = rfd::AsyncFileDialog::new()
        .set_file_name(default_name)
        .save_file()
        .await;

    if let Some(handle) = path {
        tokio::fs::write(handle.path(), bytes)
            .await
            .map_err(|e| format!("Failed to save file: {e}"))?;
    }
    Ok(())
}

/// Save text content to a file via the native save dialog.
async fn save_text_file(
    _app: &tauri::AppHandle,
    content: &str,
    default_name: &str,
) -> Result<(), String> {
    let path = rfd::AsyncFileDialog::new()
        .set_file_name(default_name)
        .save_file()
        .await;

    if let Some(handle) = path {
        tokio::fs::write(handle.path(), content.as_bytes())
            .await
            .map_err(|e| format!("Failed to save file: {e}"))?;
    }
    Ok(())
}

/// Inherit the user's shell PATH so we can find `docker`, `inspekt`, etc.
/// macOS GUI apps only get the minimal system PATH (/usr/bin:/bin:/usr/sbin:/sbin).
fn fix_path_env() {
    if let Ok(output) = std::process::Command::new("/bin/zsh")
        .args(["-ilc", "echo $PATH"])
        .output()
    {
        if let Ok(path) = String::from_utf8(output.stdout) {
            let path = path.trim();
            if !path.is_empty() {
                std::env::set_var("PATH", path);
            }
        }
    }
}

/// Configure and run the Tauri application.
#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    fix_path_env();

    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_notification::init())
        .plugin(tauri_plugin_os::init())
        .plugin(tauri_plugin_clipboard_manager::init())
        // .plugin(tauri_plugin_global_shortcut::Builder::new().build())  // temporarily disabled
        .setup(|app| {
            // Set up native menu
            let menu = menu::create_menu(app.handle())?;
            app.set_menu(menu)?;

            // Listen for VM window close — show launcher again
            let handle = app.handle().clone();
            app.listen("tauri://window-destroyed", move |event: tauri::Event| {
                // When VM window closes, show the main window
                let payload = event.payload();
                if payload.contains("vm") {
                    if let Some(main_window) = handle.get_webview_window("main") {
                        let _ = main_window.show();
                        let _ = main_window.set_focus();
                    }
                }
            });

            Ok(())
        })
        .on_menu_event(|app, event| {
            let id = event.id().0.as_str();

            match id {
                // ── VM lifecycle ─────────────────────────────────
                "vm_start" => {
                    let handle = app.clone();
                    tauri::async_runtime::spawn(async move {
                        let _ = start_vm(handle).await;
                    });
                }
                "vm_stop" => {
                    let handle = app.clone();
                    tauri::async_runtime::spawn(async move {
                        let _ = stop_vm(handle).await;
                    });
                }
                "vm_restart" => {
                    let handle = app.clone();
                    tauri::async_runtime::spawn(async move {
                        let _ = stop_vm(handle.clone()).await;
                        tokio::time::sleep(Duration::from_secs(2)).await;
                        let _ = start_vm(handle).await;
                    });
                }
                "vm_reconnect" => {
                    let handle = app.clone();
                    tauri::async_runtime::spawn(async move {
                        let _ = open_vm_window(handle).await;
                    });
                }
                "vm_open_browser" => {
                    let _ = open::that("http://localhost:6080/control.html");
                }
                "settings" => {
                    if let Err(e) = open_preferences_window(app) {
                        eprintln!("Failed to open preferences: {}", e);
                    }
                }
                "vm_restart_browser" => {
                    tauri::async_runtime::spawn(api_get("/restart-browser"));
                }
                "vm_restart_services" => {
                    tauri::async_runtime::spawn(api_get("/restart"));
                }

                // ── File menu ────────────────────────────────────
                "new_tab" => {
                    tauri::async_runtime::spawn(api_post("/tabs/new", None));
                }
                "duplicate_tab" => {
                    tauri::async_runtime::spawn(async {
                        // Get current URL, then open it in a new tab
                        if let Ok(resp) = reqwest::get(format!("{CONTROL_SERVER}/page-info")).await {
                            if let Ok(info) = resp.json::<serde_json::Value>().await {
                                if let Some(url) = info.get("url").and_then(|v| v.as_str()) {
                                    let _ = api_post(
                                        "/tabs/new",
                                        Some(serde_json::json!({ "url": url })),
                                    )
                                    .await;
                                }
                            }
                        }
                    });
                }
                "close_tab" => {
                    tauri::async_runtime::spawn(async {
                        // Close active tab via API
                        if let Ok(resp) = reqwest::get(format!("{CONTROL_SERVER}/tabs")).await {
                            if let Ok(tabs) = resp.json::<serde_json::Value>().await {
                                if let Some(active) = tabs
                                    .as_array()
                                    .and_then(|t| t.iter().find(|tab| tab["active"] == true))
                                {
                                    if let Some(id) = active.get("id").and_then(|v| v.as_str()) {
                                        let _ = api_get(&format!("/tabs/{id}/close")).await;
                                    }
                                }
                            }
                        }
                    });
                }
                "save_screenshot" => {
                    let handle = app.clone();
                    tauri::async_runtime::spawn(save_screenshot(handle, "/screenshot/viewport"));
                }
                "save_full_screenshot" => {
                    let handle = app.clone();
                    tauri::async_runtime::spawn(save_screenshot(handle, "/screenshot/page"));
                }

                // ── File > Open Location / Upload / Download ─────
                "open_location" | "upload_files" | "download_file" => {
                    emit_to_vm(app, id);
                }

                // ── File > Export ─────────────────────────────────
                "export_links_md" => {
                    tauri::async_runtime::spawn(run_inspekt(&["links", "--markdown"]));
                }
                "export_page_md" => {
                    tauri::async_runtime::spawn(run_inspekt(&["extract", "article", "--raw"]));
                }
                "export_outline" => {
                    tauri::async_runtime::spawn(run_inspekt(&["outline"]));
                }
                "export_page_info" => {
                    let handle = app.clone();
                    tauri::async_runtime::spawn(async move {
                        if let Ok(resp) = reqwest::get(format!("{CONTROL_SERVER}/page-info")).await {
                            if let Ok(body) = resp.text().await {
                                let _ = save_text_file(&handle, &body, "page-info.json").await;
                            }
                        }
                    });
                }
                "export_a11y_report" => {
                    tauri::async_runtime::spawn(run_inspekt(&["axe"]));
                }

                // ── Edit ─────────────────────────────────────────
                // Cmd+C: route through the webview. JS decides whether to
                // copy a native selection (URL bar, terminal, input) or the
                // VM's selection via the bridge. See focus-overlay.js.
                "smart_copy" => {
                    if let Some(window) = app.get_webview_window("vm") {
                        let _ = window.eval(
                            "window.__inspektSmartCopy && window.__inspektSmartCopy()",
                        );
                    }
                }
                "copy_selection" => {
                    let handle = app.clone();
                    tauri::async_runtime::spawn(
                        copy_inspekt_with_toast(handle, "selection text --raw", "Text"),
                    );
                }
                "copy_selection_markdown" => {
                    let handle = app.clone();
                    tauri::async_runtime::spawn(
                        copy_inspekt_with_toast(handle, "selection markdown --raw", "Markdown"),
                    );
                }
                "copy_selection_html" => {
                    let handle = app.clone();
                    tauri::async_runtime::spawn(
                        copy_inspekt_with_toast(handle, "selection html --raw", "HTML"),
                    );
                }
                "copy_selection_html_clean" => {
                    let handle = app.clone();
                    tauri::async_runtime::spawn(
                        copy_inspekt_with_toast(handle, "selection html --compact --raw", "Cleaned HTML"),
                    );
                }
                "copy_page_url" => {
                    let handle = app.clone();
                    tauri::async_runtime::spawn(async move {
                        if let Ok(resp) = reqwest::get(format!("{CONTROL_SERVER}/page-info")).await {
                            if let Ok(info) = resp.json::<serde_json::Value>().await {
                                if let Some(url) = info.get("url").and_then(|v| v.as_str()) {
                                    let _ = handle.clipboard().write_text(url);
                                    show_vm_toast(&handle, "URL copied!", "success");
                                }
                            }
                        }
                    });
                }
                // Clipboard relay: JS POSTs text to control server, then triggers
                // this menu action to have Rust read and copy it.
                "clipboard_relay" => {
                    let handle = app.clone();
                    tauri::async_runtime::spawn(poll_clipboard_relay(handle));
                }
                "find" => {
                    // Send Ctrl+F to VM
                    tauri::async_runtime::spawn(api_post(
                        "/keys/send",
                        Some(serde_json::json!({ "keys": "ctrl+f" })),
                    ));
                }

                // ── View ─────────────────────────────────────────
                "zoom_in" => {
                    tauri::async_runtime::spawn(api_post(
                        "/zoom",
                        Some(serde_json::json!({ "level": "+" })),
                    ));
                }
                "zoom_out" => {
                    tauri::async_runtime::spawn(api_post(
                        "/zoom",
                        Some(serde_json::json!({ "level": "-" })),
                    ));
                }
                "zoom_actual" => {
                    tauri::async_runtime::spawn(api_post(
                        "/zoom",
                        Some(serde_json::json!({ "level": 1 })),
                    ));
                }
                "devtools" => {
                    tauri::async_runtime::spawn(api_get("/devtools/toggle"));
                }
                "element_inspector" | "terminal" | "split_view" | "tab_overview" | "page_info" => {
                    emit_to_vm(app, id);
                }

                // ── Navigate ─────────────────────────────────────
                "nav_back" => {
                    tauri::async_runtime::spawn(api_get("/back"));
                }
                "nav_forward" => {
                    tauri::async_runtime::spawn(api_get("/forward"));
                }
                "reload" => {
                    tauri::async_runtime::spawn(api_get("/reload-page"));
                }
                "reload_no_cache" => {
                    tauri::async_runtime::spawn(api_get("/reload-page?clearCache=true"));
                }
                "scroll_top" => {
                    tauri::async_runtime::spawn(run_inspekt(&["top"]));
                }
                "scroll_bottom" => {
                    tauri::async_runtime::spawn(run_inspekt(&["bottom"]));
                }

                // ── Tools > Accessibility ─────────────────────────
                "run_axe" => {
                    tauri::async_runtime::spawn(run_inspekt(&["axe"]));
                }
                "run_ibm" => {
                    tauri::async_runtime::spawn(run_inspekt(&["ibm"]));
                }
                "run_a11y" => {
                    tauri::async_runtime::spawn(run_inspekt(&["a11y"]));
                }
                "check_autocomplete" => {
                    tauri::async_runtime::spawn(run_inspekt(&["autocomplete"]));
                }
                "auto_scan" => {
                    tauri::async_runtime::spawn(api_post("/settings/auto-scan", None));
                }

                // ── Tools > Screen Reader ─────────────────────────
                "sr_jaws" => {
                    tauri::async_runtime::spawn(api_post(
                        "/sr/start",
                        Some(serde_json::json!({ "screenReader": "jaws" })),
                    ));
                }
                "sr_nvda" => {
                    tauri::async_runtime::spawn(api_post(
                        "/sr/start",
                        Some(serde_json::json!({ "screenReader": "nvda" })),
                    ));
                }
                "sr_voiceover" => {
                    tauri::async_runtime::spawn(api_post(
                        "/sr/start",
                        Some(serde_json::json!({ "screenReader": "voiceover" })),
                    ));
                }
                "sr_stop" => {
                    tauri::async_runtime::spawn(api_post("/sr/stop", None));
                }
                "sr_speech" => {
                    emit_to_vm(app, "toggleSpeech");
                }

                // ── Tools > Vision Simulator ──────────────────────
                id_str if id_str.starts_with("vision_") => {
                    let sim = id_str.strip_prefix("vision_").unwrap_or("clear");
                    emit_to_vm_with_payload(app, "setVisionSimulator", sim);
                }

                // ── Tools > Motor Simulator ───────────────────────
                id_str if id_str.starts_with("motor_") => {
                    let sim = id_str.strip_prefix("motor_").unwrap_or("clear");
                    emit_to_vm_with_payload(app, "setMotorSimulator", sim);
                }

                // ── Tools > Screenshot ────────────────────────────
                "screenshot_viewport" => {
                    let handle = app.clone();
                    tauri::async_runtime::spawn(save_screenshot(handle, "/screenshot/viewport"));
                }
                "screenshot_page" => {
                    let handle = app.clone();
                    tauri::async_runtime::spawn(save_screenshot(handle, "/screenshot/page"));
                }
                "screenshot_element" => {
                    emit_to_vm(app, "screenshot_element");
                }
                "screenshot_region" => {
                    emit_to_vm(app, "screenshot_region");
                }
                "screenshot_redacted_viewport_blur" => {
                    let handle = app.clone();
                    tauri::async_runtime::spawn(save_screenshot(
                        handle,
                        "/screenshot/redacted?scope=viewport&style=blur",
                    ));
                }
                "screenshot_redacted_viewport_bars" => {
                    let handle = app.clone();
                    tauri::async_runtime::spawn(save_screenshot(
                        handle,
                        "/screenshot/redacted?scope=viewport&style=bars",
                    ));
                }
                "screenshot_redacted_page_blur" => {
                    let handle = app.clone();
                    tauri::async_runtime::spawn(save_screenshot(
                        handle,
                        "/screenshot/redacted?scope=page&style=blur",
                    ));
                }
                "screenshot_redacted_page_bars" => {
                    let handle = app.clone();
                    tauri::async_runtime::spawn(save_screenshot(
                        handle,
                        "/screenshot/redacted?scope=page&style=bars",
                    ));
                }

                // ── Tools > Recording ─────────────────────────────
                "record_start" => {
                    tauri::async_runtime::spawn(run_inspekt(&["record"]));
                }
                "record_view" => {
                    emit_to_vm(app, "viewRecordings");
                }
                "record_download" => {
                    tauri::async_runtime::spawn(api_get("/recordings/download-all"));
                }

                // ── Tools > Proxy ─────────────────────────────────
                "proxy_toggle" => {
                    tauri::async_runtime::spawn(api_post("/proxy/toggle", None));
                }
                "proxy_scripts" => {
                    emit_to_vm(app, "manageProxyScripts");
                }
                "proxy_log" => {
                    tauri::async_runtime::spawn(api_get("/proxy/log"));
                }

                // ── Tools > AI ────────────────────────────────────
                "ai_describe" => {
                    tauri::async_runtime::spawn(run_inspekt(&["describe"]));
                }
                "ai_summarize" => {
                    tauri::async_runtime::spawn(run_inspekt(&["summarize"]));
                }
                "ai_ask" => {
                    emit_to_vm(app, "aiAskPrompt");
                }
                "ai_describe_selection" => {
                    tauri::async_runtime::spawn(run_inspekt(&["selection", "describe"]));
                }
                "ai_ask_selection" => {
                    emit_to_vm(app, "aiAskSelectionPrompt");
                }

                // ── Tools > Command Palette ───────────────────────
                "command_palette" => {
                    emit_to_vm(app, "commandPalette");
                }

                // ── VM menu ───────────────────────────────────────
                "vm_audio" => {
                    emit_to_vm(app, "toggleAudio");
                }
                "theme_light" => {
                    tauri::async_runtime::spawn(api_post("/theme/light", None));
                }
                "theme_dark" => {
                    tauri::async_runtime::spawn(api_post("/theme/dark", None));
                }
                "theme_system" => {
                    emit_to_vm(app, "themeMatchSystem");
                }
                "vm_customize_toolbar" => {
                    emit_to_vm(app, "customizeToolbar");
                }

                // ── Help ─────────────────────────────────────────
                "keyboard_shortcuts" => {
                    emit_to_vm(app, "keyboardShortcuts");
                }
                "documentation" => {
                    let _ = open::that("https://inspekt.dev/docs");
                }
                "website" => {
                    let _ = open::that("https://inspekt.dev");
                }

                // ── Window ───────────────────────────────────────
                "bring_all_front" => {
                    // Handled natively on macOS, but we can iterate windows
                    for (_, window) in app.webview_windows() {
                        let _ = window.set_focus();
                    }
                }

                _ => {}
            }
        })
        .invoke_handler(tauri::generate_handler![
            check_docker,
            check_vm_status,
            start_vm,
            stop_vm,
            open_vm_window,
            get_system_accent_color,
            get_accessibility_settings,
            resize_preferences_window,
            start_dragging,
            open_tab_window,
        ])
        .build(tauri::generate_context!())
        .expect("error while building tauri application")
        .run(|_app_handle, _event| {});
}
