//! Native menu configuration for the Inspekt PDF Viewer.
//!
//! This module sets up the macOS/Windows/Linux native menu bar with
//! appropriate keyboard shortcuts and menu items.

use tauri::{
    menu::{AboutMetadataBuilder, Menu, MenuBuilder, MenuItemBuilder, PredefinedMenuItem, SubmenuBuilder},
    AppHandle, Wry,
};

/// Create the application menu.
pub fn create_menu(app: &AppHandle) -> Result<Menu<Wry>, tauri::Error> {
    // File menu
    let file_menu = SubmenuBuilder::new(app, "File")
        .items(&[
            &MenuItemBuilder::with_id("open", "Open...")
                .accelerator("CmdOrCtrl+O")
                .build(app)?,
            &MenuItemBuilder::with_id("open_recent", "Open Recent")
                .enabled(false) // Will be dynamically updated
                .build(app)?,
            &PredefinedMenuItem::separator(app)?,
            &MenuItemBuilder::with_id("save", "Save")
                .accelerator("CmdOrCtrl+S")
                .build(app)?,
            &MenuItemBuilder::with_id("save_as", "Save As...")
                .accelerator("CmdOrCtrl+Shift+S")
                .build(app)?,
            &PredefinedMenuItem::separator(app)?,
            &MenuItemBuilder::with_id("close", "Close")
                .accelerator("CmdOrCtrl+W")
                .build(app)?,
        ])
        .build()?;

    // Edit menu
    let edit_menu = SubmenuBuilder::new(app, "Edit")
        .items(&[
            &PredefinedMenuItem::undo(app, Some("Undo"))?,
            &PredefinedMenuItem::redo(app, Some("Redo"))?,
            &PredefinedMenuItem::separator(app)?,
            &PredefinedMenuItem::cut(app, Some("Cut"))?,
            &PredefinedMenuItem::copy(app, Some("Copy"))?,
            &PredefinedMenuItem::paste(app, Some("Paste"))?,
            &PredefinedMenuItem::select_all(app, Some("Select All"))?,
        ])
        .build()?;

    // View menu
    let view_menu = SubmenuBuilder::new(app, "View")
        .items(&[
            &MenuItemBuilder::with_id("toggle_sidebar", "Toggle Sidebar")
                .accelerator("CmdOrCtrl+Shift+S")
                .build(app)?,
            &PredefinedMenuItem::separator(app)?,
            &MenuItemBuilder::with_id("zoom_in", "Zoom In")
                .accelerator("CmdOrCtrl+Plus")
                .build(app)?,
            &MenuItemBuilder::with_id("zoom_out", "Zoom Out")
                .accelerator("CmdOrCtrl+Minus")
                .build(app)?,
            &MenuItemBuilder::with_id("zoom_reset", "Actual Size")
                .accelerator("CmdOrCtrl+0")
                .build(app)?,
            &MenuItemBuilder::with_id("zoom_fit", "Zoom to Fit")
                .accelerator("CmdOrCtrl+9")
                .build(app)?,
            &PredefinedMenuItem::separator(app)?,
            &PredefinedMenuItem::fullscreen(app, Some("Toggle Fullscreen"))?,
        ])
        .build()?;

    // Window menu
    let window_menu = SubmenuBuilder::new(app, "Window")
        .items(&[
            &PredefinedMenuItem::minimize(app, Some("Minimize"))?,
            &MenuItemBuilder::with_id("zoom_window", "Zoom")
                .build(app)?,
            &PredefinedMenuItem::separator(app)?,
            &PredefinedMenuItem::close_window(app, Some("Close Window"))?,
        ])
        .build()?;

    // Help menu
    let help_menu = SubmenuBuilder::new(app, "Help")
        .items(&[
            &MenuItemBuilder::with_id("documentation", "Documentation")
                .build(app)?,
            &MenuItemBuilder::with_id("website", "Inspekt Website")
                .build(app)?,
        ])
        .build()?;

    // Build the complete menu
    #[cfg(target_os = "macos")]
    {
        // On macOS, include the app menu with Preferences
        let app_menu = SubmenuBuilder::new(app, "Inspekt PDF Viewer")
            .items(&[
                &PredefinedMenuItem::about(
                    app,
                    Some("About Inspekt PDF Viewer"),
                    Some(
                        AboutMetadataBuilder::new()
                            .name(Some("Inspekt PDF Viewer"))
                            .version(Some("0.1.0"))
                            .copyright(Some("© 2025 Fronteers"))
                            .license(Some("MIT"))
                            .website(Some("https://inspekt.dev"))
                            .website_label(Some("Visit Inspekt"))
                            .build(),
                    ),
                )?,
                &PredefinedMenuItem::separator(app)?,
                &MenuItemBuilder::with_id("preferences", "Settings...")
                    .accelerator("CmdOrCtrl+,")
                    .build(app)?,
                &PredefinedMenuItem::separator(app)?,
                &PredefinedMenuItem::services(app, Some("Services"))?,
                &PredefinedMenuItem::separator(app)?,
                &PredefinedMenuItem::hide(app, Some("Hide Inspekt PDF Viewer"))?,
                &PredefinedMenuItem::hide_others(app, Some("Hide Others"))?,
                &PredefinedMenuItem::show_all(app, Some("Show All"))?,
                &PredefinedMenuItem::separator(app)?,
                &PredefinedMenuItem::quit(app, Some("Quit Inspekt PDF Viewer"))?,
            ])
            .build()?;

        MenuBuilder::new(app)
            .items(&[
                &app_menu,
                &file_menu,
                &edit_menu,
                &view_menu,
                &window_menu,
                &help_menu,
            ])
            .build()
    }

    #[cfg(not(target_os = "macos"))]
    {
        // On Windows/Linux, add Preferences to Edit menu
        let edit_menu_with_prefs = SubmenuBuilder::new(app, "Edit")
            .items(&[
                &PredefinedMenuItem::undo(app, Some("Undo"))?,
                &PredefinedMenuItem::redo(app, Some("Redo"))?,
                &PredefinedMenuItem::separator(app)?,
                &PredefinedMenuItem::cut(app, Some("Cut"))?,
                &PredefinedMenuItem::copy(app, Some("Copy"))?,
                &PredefinedMenuItem::paste(app, Some("Paste"))?,
                &PredefinedMenuItem::select_all(app, Some("Select All"))?,
                &PredefinedMenuItem::separator(app)?,
                &MenuItemBuilder::with_id("preferences", "Settings...")
                    .accelerator("CmdOrCtrl+,")
                    .build(app)?,
            ])
            .build()?;

        MenuBuilder::new(app)
            .items(&[
                &file_menu,
                &edit_menu_with_prefs,
                &view_menu,
                &window_menu,
                &help_menu,
            ])
            .build()
    }
}
