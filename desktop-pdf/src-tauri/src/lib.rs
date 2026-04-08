//! Inspekt PDF Viewer - Tauri backend library
//!
//! This module provides the Rust backend for the Inspekt PDF Viewer desktop application.
//! It handles file operations, PDF checking via the inspekt CLI, and native OS integration.

pub mod commands;
pub mod menu;

use serde::{Deserialize, Serialize};
use tauri::{Emitter, Listener, Manager, WebviewUrl, WebviewWindowBuilder};

#[cfg(target_os = "macos")]
use window_vibrancy::{apply_vibrancy, NSVisualEffectMaterial};

#[cfg(target_os = "macos")]
use objc2_app_kit::{NSColor, NSColorSpace, NSWorkspace};

/// macOS accessibility settings from System Settings → Accessibility → Display.
/// These settings allow users to customize their visual experience.
#[derive(Serialize, Deserialize, Debug, Clone, Default)]
#[serde(rename_all = "camelCase")]
pub struct AccessibilitySettings {
    /// User has enabled "Reduce transparency" - skip vibrancy, use solid backgrounds
    pub reduce_transparency: bool,
    /// User has enabled "Increase contrast" - use higher contrast text colors
    pub increase_contrast: bool,
    /// User has enabled "Reduce motion" - disable/simplify animations
    pub reduce_motion: bool,
    /// User has enabled "Differentiate without color" - don't rely on color alone
    pub differentiate_without_color: bool,
    /// User has enabled "Invert colors" - informational, handled by OS
    pub invert_colors: bool,
    /// User's chosen accent color from System Settings → Appearance
    pub accent_color: String,
}

/// Get the macOS system accent color as a hex string (internal helper).
/// Returns the user's chosen accent color from System Settings → Appearance.
#[cfg(target_os = "macos")]
fn get_accent_color_hex() -> String {
    // Get NSColor.controlAccentColor (macOS 10.14+)
    let accent_color = NSColor::controlAccentColor();

    // Convert to sRGB color space for consistent hex values
    let color_space = NSColorSpace::sRGBColorSpace();

    if let Some(rgb_color) = accent_color.colorUsingColorSpace(&color_space) {
        // Extract RGB components (0.0 - 1.0)
        let red = rgb_color.redComponent();
        let green = rgb_color.greenComponent();
        let blue = rgb_color.blueComponent();

        // Convert to hex
        let r = (red * 255.0).round() as u8;
        let g = (green * 255.0).round() as u8;
        let b = (blue * 255.0).round() as u8;

        format!("#{:02X}{:02X}{:02X}", r, g, b)
    } else {
        // Fallback if conversion fails
        "#007AFF".to_string() // macOS default blue
    }
}

/// Get all macOS accessibility settings (internal helper for vibrancy decision).
/// Uses NSWorkspace accessibility APIs (macOS 10.14+).
#[cfg(target_os = "macos")]
fn get_accessibility_settings_internal() -> AccessibilitySettings {
    let workspace = NSWorkspace::sharedWorkspace();

    AccessibilitySettings {
        reduce_transparency: workspace.accessibilityDisplayShouldReduceTransparency(),
        increase_contrast: workspace.accessibilityDisplayShouldIncreaseContrast(),
        reduce_motion: workspace.accessibilityDisplayShouldReduceMotion(),
        differentiate_without_color: workspace
            .accessibilityDisplayShouldDifferentiateWithoutColor(),
        invert_colors: workspace.accessibilityDisplayShouldInvertColors(),
        accent_color: get_accent_color_hex(),
    }
}

/// Get the macOS system accent color as a hex string.
/// Returns the user's chosen accent color from System Settings → Appearance.
#[cfg(target_os = "macos")]
#[tauri::command]
fn get_system_accent_color() -> String {
    get_accent_color_hex()
}

/// Fallback for non-macOS platforms - returns default blue.
#[cfg(not(target_os = "macos"))]
#[tauri::command]
fn get_system_accent_color() -> String {
    "#007AFF".to_string()
}

/// Get all macOS accessibility settings from System Settings → Accessibility → Display.
/// These settings help the app respect user preferences for visual accessibility.
#[cfg(target_os = "macos")]
#[tauri::command]
fn get_accessibility_settings() -> AccessibilitySettings {
    get_accessibility_settings_internal()
}

/// Fallback for non-macOS platforms - returns default values (all false).
#[cfg(not(target_os = "macos"))]
#[tauri::command]
fn get_accessibility_settings() -> AccessibilitySettings {
    AccessibilitySettings {
        reduce_transparency: false,
        increase_contrast: false,
        reduce_motion: false,
        differentiate_without_color: false,
        invert_colors: false,
        accent_color: "#007AFF".to_string(),
    }
}

/// Log messages from the frontend to the terminal (debug only).
#[cfg(debug_assertions)]
#[tauri::command]
fn log_from_frontend(level: String, message: String) {
    match level.as_str() {
        "error" => eprintln!("[JS ERROR] {}", message),
        "warn" => eprintln!("[JS WARN] {}", message),
        _ => println!("[JS LOG] {}", message),
    }
}

/// No-op in release builds.
#[cfg(not(debug_assertions))]
#[tauri::command]
fn log_from_frontend(_level: String, _message: String) {}

/// Open a file with the system's default application.
#[tauri::command]
fn open_file_with_default_app(path: String) -> Result<(), String> {
    open::that(&path).map_err(|e| format!("Failed to open file: {}", e))
}

/// Set the dock badge on macOS.
#[cfg(target_os = "macos")]
#[tauri::command]
fn set_dock_badge(count: Option<u32>) -> Result<(), String> {
    // macOS dock badge is set via NSApplication
    // For now, we'll use a simple approach - just log
    // The actual implementation requires cocoa bindings
    if let Some(c) = count {
        if c > 0 {
            // Badge will be shown
            println!("[Dock] Badge set to: {}", c);
        }
    }
    Ok(())
}

#[cfg(not(target_os = "macos"))]
#[tauri::command]
fn set_dock_badge(_count: Option<u32>) -> Result<(), String> {
    // No-op on non-macOS platforms
    Ok(())
}

/// Show a native notification.
#[tauri::command]
async fn show_notification(
    app: tauri::AppHandle,
    title: String,
    body: String,
) -> Result<(), String> {
    use tauri_plugin_notification::NotificationExt;

    app.notification()
        .builder()
        .title(&title)
        .body(&body)
        .show()
        .map_err(|e| format!("Failed to show notification: {}", e))
}

/// Resize the preferences window height (for tab content auto-sizing).
#[tauri::command]
async fn resize_preferences_window(app: tauri::AppHandle, height: f64) -> Result<(), String> {
    if let Some(window) = app.get_webview_window("preferences") {
        // Fixed width of 500, variable height
        window
            .set_size(tauri::Size::Logical(tauri::LogicalSize {
                width: 500.0,
                height,
            }))
            .map_err(|e| e.to_string())?;
    }
    Ok(())
}

/// Open the preferences window.
fn open_preferences_window(app: &tauri::AppHandle) -> Result<(), tauri::Error> {
    // Check if preferences window already exists
    if let Some(window) = app.get_webview_window("preferences") {
        window.set_focus()?;
        return Ok(());
    }

    // Create new preferences window with transparency for vibrancy
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
    .transparent(true) // Required for vibrancy effect
    .title_bar_style(tauri::TitleBarStyle::Overlay)
    .hidden_title(true) // Hide native title, we render our own centered
    .build()?;

    // Apply vibrancy effect on macOS for native frosted glass appearance
    // Only apply if user hasn't enabled "Reduce transparency" in Accessibility settings
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

/// Configure and run the Tauri application.
#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_fs::init())
        .plugin(tauri_plugin_store::Builder::new().build())
        .plugin(tauri_plugin_window_state::Builder::default().build())
        .plugin(tauri_plugin_notification::init())
        .plugin(tauri_plugin_deep_link::init())
        .plugin(tauri_plugin_os::init())
        .setup(|app| {
            // Set up the native menu
            let menu = menu::create_menu(app.handle())?;
            app.set_menu(menu)?;

            // Set up drag-and-drop handling via window events
            let window = app.get_webview_window("main").unwrap();
            let window_clone = window.clone();
            let window_clone_for_args = window.clone();

            // Listen for file drop events
            window.listen("tauri://drag-drop", move |event| {
                let payload = event.payload();
                if let Ok(data) = serde_json::from_str::<serde_json::Value>(payload) {
                    if let Some(paths) = data.get("paths").and_then(|p| p.as_array()) {
                        if let Some(first_path) = paths.first().and_then(|p| p.as_str()) {
                            let _ = window_clone.emit("file-dropped", first_path.to_string());
                        }
                    }
                }
            });

            // Handle files passed via command line (double-click to open)
            // On macOS, files are passed as arguments when app is launched
            let args: Vec<String> = std::env::args().collect();
            for arg in args.iter().skip(1) {
                // Check if it's a file path (not a flag)
                if !arg.starts_with('-') {
                    let lower = arg.to_lowercase();
                    if lower.ends_with(".pdfi") || lower.ends_with(".json") || lower.ends_with(".pdf") {
                        // Delay emission to ensure frontend is ready
                        let path = arg.clone();
                        let window_for_emit = window_clone_for_args.clone();
                        std::thread::spawn(move || {
                            // Wait for frontend to initialize
                            std::thread::sleep(std::time::Duration::from_millis(500));
                            let _ = window_for_emit.emit("file-dropped", path);
                        });
                        break; // Only handle the first file
                    }
                }
            }

            // Set up deep link handler
            #[cfg(any(target_os = "linux", target_os = "macos", target_os = "windows"))]
            {
                let handle = app.handle().clone();
                app.listen("deep-link://new-url", move |event| {
                    let payload = event.payload();
                    if let Some(window) = handle.get_webview_window("main") {
                        let _ = window.emit("deep-link", payload.to_string());
                    }
                });
            }

            Ok(())
        })
        .on_menu_event(|app, event| {
            let window = app.get_webview_window("main");
            match event.id().as_ref() {
                "open" => {
                    if let Some(w) = window {
                        let _ = w.emit("menu-open", ());
                    }
                }
                "close" => {
                    if let Some(w) = window {
                        let _ = w.emit("menu-close", ());
                    }
                }
                "save" => {
                    if let Some(w) = window {
                        let _ = w.emit("menu-save", ());
                    }
                }
                "save_as" => {
                    if let Some(w) = window {
                        let _ = w.emit("menu-save-as", ());
                    }
                }
                "preferences" => {
                    if let Err(e) = open_preferences_window(app) {
                        eprintln!("Failed to open preferences: {}", e);
                    }
                }
                "toggle_sidebar" => {
                    if let Some(w) = window {
                        let _ = w.emit("menu-toggle-sidebar", ());
                    }
                }
                "zoom_in" => {
                    if let Some(w) = window {
                        let _ = w.emit("menu-zoom-in", ());
                    }
                }
                "zoom_out" => {
                    if let Some(w) = window {
                        let _ = w.emit("menu-zoom-out", ());
                    }
                }
                "zoom_reset" => {
                    if let Some(w) = window {
                        let _ = w.emit("menu-zoom-reset", ());
                    }
                }
                "zoom_fit" => {
                    if let Some(w) = window {
                        let _ = w.emit("menu-zoom-fit", ());
                    }
                }
                "documentation" => {
                    let _ = open::that("https://inspekt.dev/docs");
                }
                "website" => {
                    let _ = open::that("https://inspekt.dev");
                }
                _ => {}
            }
        })
        .invoke_handler(tauri::generate_handler![
            commands::file_ops::read_json_file,
            commands::file_ops::get_file_info,
            commands::file_ops::extract_pdfi_package,
            commands::file_ops::cleanup_pdfi_extraction,
            commands::file_ops::save_as_pdfi,
            commands::pdf_check::check_pdf,
            commands::pdf_check::cancel_check,
            log_from_frontend,
            open_file_with_default_app,
            set_dock_badge,
            show_notification,
            resize_preferences_window,
            get_system_accent_color,
            get_accessibility_settings,
        ])
        .build(tauri::generate_context!())
        .expect("error while building tauri application")
        .run(|app_handle, event| {
            // Handle macOS file open events (when app is already running)
            #[cfg(target_os = "macos")]
            if let tauri::RunEvent::Opened { urls } = &event {
                for url in urls {
                    // Convert URL to file path
                    if let Ok(path) = url.to_file_path() {
                        if let Some(path_str) = path.to_str() {
                            let lower = path_str.to_lowercase();
                            if lower.ends_with(".pdfi") || lower.ends_with(".json") || lower.ends_with(".pdf") {
                                if let Some(window) = app_handle.get_webview_window("main") {
                                    let _ = window.emit("file-dropped", path_str.to_string());
                                }
                                break;
                            }
                        }
                    }
                }
            }
            // Suppress unused variable warning on non-macOS
            let _ = (app_handle, event);
        });
}
