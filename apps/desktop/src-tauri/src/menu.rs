use tauri::{
    menu::{
        AboutMetadataBuilder, CheckMenuItemBuilder, Menu, MenuBuilder, MenuItemBuilder,
        PredefinedMenuItem, SubmenuBuilder,
    },
    AppHandle, Wry,
};

pub fn create_menu(app: &AppHandle) -> Result<Menu<Wry>, tauri::Error> {
    // ── File menu ────────────────────────────────────────────────────

    let export_submenu = SubmenuBuilder::new(app, "Export")
        .items(&[
            &MenuItemBuilder::with_id("export_links_md", "Export Links as Markdown")
                .build(app)?,
            &MenuItemBuilder::with_id("export_page_md", "Export Page as Markdown")
                .build(app)?,
            &MenuItemBuilder::with_id("export_outline", "Export Heading Outline")
                .build(app)?,
            &MenuItemBuilder::with_id("export_page_info", "Export Page Info as JSON")
                .build(app)?,
            &PredefinedMenuItem::separator(app)?,
            &MenuItemBuilder::with_id("export_a11y_report", "Export Accessibility Report\u{2026}")
                .build(app)?,
        ])
        .build()?;

    let file_menu = SubmenuBuilder::new(app, "File")
        .items(&[
            &MenuItemBuilder::with_id("new_tab", "New Tab")
                .accelerator("CmdOrCtrl+T")
                .build(app)?,
            &MenuItemBuilder::with_id("duplicate_tab", "Duplicate Tab")
                .build(app)?,
            &MenuItemBuilder::with_id("open_location", "Open Location\u{2026}")
                .accelerator("CmdOrCtrl+L")
                .build(app)?,
            &PredefinedMenuItem::separator(app)?,
            &MenuItemBuilder::with_id("close_tab", "Close Tab")
                .accelerator("CmdOrCtrl+W")
                .build(app)?,
            &PredefinedMenuItem::separator(app)?,
            &MenuItemBuilder::with_id("save_screenshot", "Save Screenshot\u{2026}")
                .accelerator("CmdOrCtrl+S")
                .build(app)?,
            &MenuItemBuilder::with_id("save_full_screenshot", "Save Full Page Screenshot\u{2026}")
                .accelerator("CmdOrCtrl+Shift+S")
                .build(app)?,
            &PredefinedMenuItem::separator(app)?,
            &MenuItemBuilder::with_id("upload_files", "Upload Files\u{2026}")
                .build(app)?,
            &MenuItemBuilder::with_id("download_file", "Download File\u{2026}")
                .build(app)?,
            &PredefinedMenuItem::separator(app)?,
            &export_submenu,
        ])
        .build()?;

    // ── Edit menu ────────────────────────────────────────────────────

    // Copy submenu: copy selected text from the VM browser in various formats.
    // Submenu items always do VM-side copy when clicked. The Cmd+C shortcut
    // lives on a separate "Copy" item (`smart_copy`) that routes through the
    // webview so native inputs/terminal/URL bar copy still works.
    let copy_submenu = SubmenuBuilder::new(app, "Copy From VM")
        .items(&[
            &MenuItemBuilder::with_id("copy_selection", "Copy as Text")
                .build(app)?,
            &MenuItemBuilder::with_id("copy_selection_markdown", "Copy as Markdown")
                .build(app)?,
            &MenuItemBuilder::with_id("copy_selection_html", "Copy as HTML")
                .build(app)?,
            &MenuItemBuilder::with_id("copy_selection_html_clean", "Copy as HTML (Cleaned)")
                .build(app)?,
            &PredefinedMenuItem::separator(app)?,
            &MenuItemBuilder::with_id("copy_page_url", "Copy Page URL")
                .build(app)?,
        ])
        .build()?;

    let edit_menu = SubmenuBuilder::new(app, "Edit")
        .items(&[
            &PredefinedMenuItem::undo(app, Some("Undo"))?,
            &PredefinedMenuItem::redo(app, Some("Redo"))?,
            &PredefinedMenuItem::separator(app)?,
            &PredefinedMenuItem::cut(app, Some("Cut"))?,
            &MenuItemBuilder::with_id("smart_copy", "Copy")
                .accelerator("CmdOrCtrl+C")
                .build(app)?,
            &copy_submenu,
            &PredefinedMenuItem::paste(app, Some("Paste"))?,
            &PredefinedMenuItem::select_all(app, Some("Select All"))?,
            &PredefinedMenuItem::separator(app)?,
            &MenuItemBuilder::with_id("find", "Find\u{2026}")
                .accelerator("CmdOrCtrl+F")
                .build(app)?,
        ])
        .build()?;

    // ── View menu ────────────────────────────────────────────────────

    let view_menu = SubmenuBuilder::new(app, "View")
        .items(&[
            &MenuItemBuilder::with_id("zoom_in", "Zoom In")
                .accelerator("CmdOrCtrl+Plus")
                .build(app)?,
            &MenuItemBuilder::with_id("zoom_out", "Zoom Out")
                .accelerator("CmdOrCtrl+Minus")
                .build(app)?,
            &MenuItemBuilder::with_id("zoom_actual", "Actual Size")
                .accelerator("CmdOrCtrl+0")
                .build(app)?,
            &PredefinedMenuItem::separator(app)?,
            &CheckMenuItemBuilder::with_id("devtools", "DevTools")
                .accelerator("CmdOrCtrl+Alt+I")
                .build(app)?,
            &CheckMenuItemBuilder::with_id("element_inspector", "Element Inspector")
                .accelerator("CmdOrCtrl+Alt+C")
                .build(app)?,
            &MenuItemBuilder::with_id("reload_window", "Reload Window")
                .accelerator("CmdOrCtrl+Alt+R")
                .build(app)?,
            &PredefinedMenuItem::separator(app)?,
            &CheckMenuItemBuilder::with_id("terminal", "Terminal")
                .accelerator("CmdOrCtrl+\\")
                .build(app)?,
            &CheckMenuItemBuilder::with_id("split_view", "Split View")
                .build(app)?,
            &PredefinedMenuItem::separator(app)?,
            &MenuItemBuilder::with_id("tab_overview", "Tab Overview")
                .accelerator("CmdOrCtrl+Shift+\\")
                .build(app)?,
            &PredefinedMenuItem::separator(app)?,
            &MenuItemBuilder::with_id("page_info", "Page Info")
                .accelerator("CmdOrCtrl+I")
                .build(app)?,
            &PredefinedMenuItem::separator(app)?,
            &PredefinedMenuItem::fullscreen(app, Some("Enter Full Screen"))?,
        ])
        .build()?;

    // ── Navigate menu ────────────────────────────────────────────────

    let navigate_menu = SubmenuBuilder::new(app, "Navigate")
        .items(&[
            &MenuItemBuilder::with_id("nav_back", "Back")
                .accelerator("CmdOrCtrl+[")
                .build(app)?,
            &MenuItemBuilder::with_id("nav_forward", "Forward")
                .accelerator("CmdOrCtrl+]")
                .build(app)?,
            &PredefinedMenuItem::separator(app)?,
            &MenuItemBuilder::with_id("reload", "Reload Page")
                .accelerator("CmdOrCtrl+R")
                .build(app)?,
            &MenuItemBuilder::with_id("reload_no_cache", "Reload Without Cache")
                .accelerator("CmdOrCtrl+Shift+R")
                .build(app)?,
            &PredefinedMenuItem::separator(app)?,
            &MenuItemBuilder::with_id("scroll_top", "Scroll to Top")
                .build(app)?,
            &MenuItemBuilder::with_id("scroll_bottom", "Scroll to Bottom")
                .build(app)?,
        ])
        .build()?;

    // ── Tools menu ───────────────────────────────────────────────────

    // Tools > Accessibility
    let a11y_submenu = SubmenuBuilder::new(app, "Accessibility")
        .items(&[
            &MenuItemBuilder::with_id("run_axe", "Run axe Audit")
                .accelerator("CmdOrCtrl+Shift+A")
                .build(app)?,
            &MenuItemBuilder::with_id("run_ibm", "Run IBM Audit")
                .build(app)?,
            &MenuItemBuilder::with_id("run_a11y", "Run WCAG Evaluation")
                .build(app)?,
            &MenuItemBuilder::with_id("check_autocomplete", "Check Autocomplete")
                .build(app)?,
            &PredefinedMenuItem::separator(app)?,
            &CheckMenuItemBuilder::with_id("auto_scan", "Auto-Scan")
                .build(app)?,
        ])
        .build()?;

    // Tools > Screen Reader
    let sr_submenu = SubmenuBuilder::new(app, "Screen Reader")
        .items(&[
            &MenuItemBuilder::with_id("sr_jaws", "Start JAWS")
                .build(app)?,
            &MenuItemBuilder::with_id("sr_nvda", "Start NVDA")
                .build(app)?,
            &MenuItemBuilder::with_id("sr_voiceover", "Start VoiceOver")
                .build(app)?,
            &PredefinedMenuItem::separator(app)?,
            &MenuItemBuilder::with_id("sr_stop", "Stop Simulation")
                .build(app)?,
            &CheckMenuItemBuilder::with_id("sr_speech", "Speech Output")
                .build(app)?,
        ])
        .build()?;

    // Tools > Vision Simulator > Color Blindness
    let color_blindness_submenu = SubmenuBuilder::new(app, "Color Blindness")
        .items(&[
            &MenuItemBuilder::with_id("vision_protanopia", "Protanopia (Red-Blind)")
                .build(app)?,
            &MenuItemBuilder::with_id("vision_deuteranopia", "Deuteranopia (Green-Blind)")
                .build(app)?,
            &MenuItemBuilder::with_id("vision_tritanopia", "Tritanopia (Blue-Blind)")
                .build(app)?,
            &MenuItemBuilder::with_id("vision_achromatopsia", "Achromatopsia (Total)")
                .build(app)?,
        ])
        .build()?;

    // Tools > Vision Simulator > Low Vision
    let low_vision_submenu = SubmenuBuilder::new(app, "Low Vision")
        .items(&[
            &MenuItemBuilder::with_id("vision_low_vision", "Low Vision (20/100)")
                .build(app)?,
            &MenuItemBuilder::with_id("vision_near_total", "Near-Total Loss")
                .build(app)?,
            &MenuItemBuilder::with_id("vision_light_only", "Light Perception Only")
                .build(app)?,
        ])
        .build()?;

    // Tools > Vision Simulator > Eye Conditions
    let eye_conditions_submenu = SubmenuBuilder::new(app, "Eye Conditions")
        .items(&[
            &MenuItemBuilder::with_id("vision_cataracts", "Cataracts")
                .build(app)?,
            &MenuItemBuilder::with_id("vision_glaucoma", "Glaucoma")
                .build(app)?,
            &MenuItemBuilder::with_id("vision_tunnel", "Tunnel Vision")
                .build(app)?,
            &MenuItemBuilder::with_id("vision_scotoma", "Central Scotoma (AMD)")
                .build(app)?,
            &MenuItemBuilder::with_id("vision_hemianopia", "Hemianopia")
                .build(app)?,
            &MenuItemBuilder::with_id("vision_keratoconus", "Keratoconus")
                .build(app)?,
            &MenuItemBuilder::with_id("vision_corneal", "Corneal Scarring")
                .build(app)?,
            &MenuItemBuilder::with_id("vision_floaters", "Diabetic Floaters")
                .build(app)?,
        ])
        .build()?;

    // Tools > Vision Simulator > Movement Disorders
    let movement_submenu = SubmenuBuilder::new(app, "Movement Disorders")
        .items(&[
            &MenuItemBuilder::with_id("vision_nystagmus", "Nystagmus")
                .build(app)?,
            &MenuItemBuilder::with_id("vision_diplopia", "Diplopia (Double Vision)")
                .build(app)?,
            &MenuItemBuilder::with_id("vision_metamorphopsia", "Metamorphopsia (Wavy Lines)")
                .build(app)?,
            &MenuItemBuilder::with_id("vision_snow", "Visual Snow")
                .build(app)?,
        ])
        .build()?;

    // Tools > Vision Simulator
    let vision_submenu = SubmenuBuilder::new(app, "Vision Simulator")
        .items(&[
            &MenuItemBuilder::with_id("vision_clear", "Normal (Clear)")
                .build(app)?,
            &PredefinedMenuItem::separator(app)?,
            &color_blindness_submenu,
            &low_vision_submenu,
            &eye_conditions_submenu,
            &movement_submenu,
        ])
        .build()?;

    // Tools > Motor Simulator
    let motor_submenu = SubmenuBuilder::new(app, "Motor Simulator")
        .items(&[
            &MenuItemBuilder::with_id("motor_clear", "Normal (Clear)")
                .build(app)?,
            &PredefinedMenuItem::separator(app)?,
            &MenuItemBuilder::with_id("motor_parkinsons", "Parkinson's Tremor")
                .build(app)?,
            &MenuItemBuilder::with_id("motor_essential", "Essential Tremor")
                .build(app)?,
            &MenuItemBuilder::with_id("motor_spasms", "Muscle Spasms")
                .build(app)?,
            &MenuItemBuilder::with_id("motor_fine", "Limited Fine Motor")
                .build(app)?,
        ])
        .build()?;

    // Tools > Screenshot > Redacted Screenshot
    let redacted_submenu = SubmenuBuilder::new(app, "Redacted Screenshot")
        .items(&[
            &MenuItemBuilder::with_id("screenshot_redacted_viewport_blur", "Viewport (Blurred)")
                .build(app)?,
            &MenuItemBuilder::with_id("screenshot_redacted_viewport_bars", "Viewport (Bars)")
                .build(app)?,
            &MenuItemBuilder::with_id("screenshot_redacted_page_blur", "Full Page (Blurred)")
                .build(app)?,
            &MenuItemBuilder::with_id("screenshot_redacted_page_bars", "Full Page (Bars)")
                .build(app)?,
        ])
        .build()?;

    // Tools > Screenshot
    let screenshot_submenu = SubmenuBuilder::new(app, "Screenshot")
        .items(&[
            &MenuItemBuilder::with_id("screenshot_viewport", "Capture Viewport")
                .accelerator("CmdOrCtrl+Shift+3")
                .build(app)?,
            &MenuItemBuilder::with_id("screenshot_page", "Capture Full Page")
                .accelerator("CmdOrCtrl+Shift+4")
                .build(app)?,
            &MenuItemBuilder::with_id("screenshot_element", "Capture Element\u{2026}")
                .accelerator("CmdOrCtrl+Shift+5")
                .build(app)?,
            &MenuItemBuilder::with_id("screenshot_region", "Select Region\u{2026}")
                .build(app)?,
            &PredefinedMenuItem::separator(app)?,
            &redacted_submenu,
        ])
        .build()?;

    // Tools > Recording
    let recording_submenu = SubmenuBuilder::new(app, "Recording")
        .items(&[
            &MenuItemBuilder::with_id("record_start", "Start Recording\u{2026}")
                .build(app)?,
            &PredefinedMenuItem::separator(app)?,
            &MenuItemBuilder::with_id("record_view", "View Recordings\u{2026}")
                .build(app)?,
            &MenuItemBuilder::with_id("record_download", "Download All Recordings")
                .build(app)?,
        ])
        .build()?;

    // Tools > Proxy
    let proxy_submenu = SubmenuBuilder::new(app, "Proxy")
        .items(&[
            &CheckMenuItemBuilder::with_id("proxy_toggle", "Enable Proxy")
                .build(app)?,
            &PredefinedMenuItem::separator(app)?,
            &MenuItemBuilder::with_id("proxy_scripts", "Manage Scripts\u{2026}")
                .build(app)?,
            &MenuItemBuilder::with_id("proxy_log", "View Proxy Log\u{2026}")
                .build(app)?,
        ])
        .build()?;

    // Tools > AI Tools
    let ai_submenu = SubmenuBuilder::new(app, "AI Tools")
        .items(&[
            &MenuItemBuilder::with_id("ai_describe", "Describe Page")
                .build(app)?,
            &MenuItemBuilder::with_id("ai_summarize", "Summarize Article")
                .build(app)?,
            &MenuItemBuilder::with_id("ai_ask", "Ask About Page\u{2026}")
                .build(app)?,
            &PredefinedMenuItem::separator(app)?,
            &MenuItemBuilder::with_id("ai_describe_selection", "Describe Selection")
                .enabled(false)
                .build(app)?,
            &MenuItemBuilder::with_id("ai_ask_selection", "Ask About Selection\u{2026}")
                .enabled(false)
                .build(app)?,
        ])
        .build()?;

    // Tools (top-level)
    let tools_menu = SubmenuBuilder::new(app, "Tools")
        .items(&[
            &a11y_submenu,
            &sr_submenu,
            &vision_submenu,
            &motor_submenu,
            &PredefinedMenuItem::separator(app)?,
            &screenshot_submenu,
            &recording_submenu,
            &PredefinedMenuItem::separator(app)?,
            &proxy_submenu,
            &PredefinedMenuItem::separator(app)?,
            &ai_submenu,
            &PredefinedMenuItem::separator(app)?,
            &MenuItemBuilder::with_id("command_palette", "Command Palette\u{2026}")
                .accelerator("CmdOrCtrl+K")
                .build(app)?,
        ])
        .build()?;

    // ── VM menu ──────────────────────────────────────────────────────

    let theme_submenu = SubmenuBuilder::new(app, "Theme")
        .items(&[
            &MenuItemBuilder::with_id("theme_light", "Light")
                .build(app)?,
            &MenuItemBuilder::with_id("theme_dark", "Dark")
                .build(app)?,
            &MenuItemBuilder::with_id("theme_system", "Match System")
                .build(app)?,
        ])
        .build()?;

    let vm_menu = SubmenuBuilder::new(app, "VM")
        .items(&[
            &MenuItemBuilder::with_id("vm_start", "Start VM")
                .build(app)?,
            &MenuItemBuilder::with_id("vm_stop", "Stop VM")
                .build(app)?,
            &MenuItemBuilder::with_id("vm_restart", "Restart VM")
                .build(app)?,
            &PredefinedMenuItem::separator(app)?,
            &MenuItemBuilder::with_id("vm_restart_browser", "Restart Browser")
                .build(app)?,
            &MenuItemBuilder::with_id("vm_restart_services", "Restart All Services")
                .build(app)?,
            &PredefinedMenuItem::separator(app)?,
            &MenuItemBuilder::with_id("vm_reconnect", "Reconnect")
                .build(app)?,
            &MenuItemBuilder::with_id("vm_open_browser", "Open in Browser")
                .accelerator("CmdOrCtrl+Shift+B")
                .build(app)?,
            &PredefinedMenuItem::separator(app)?,
            &CheckMenuItemBuilder::with_id("vm_audio", "Audio")
                .build(app)?,
            &theme_submenu,
            &PredefinedMenuItem::separator(app)?,
            &MenuItemBuilder::with_id("vm_customize_toolbar", "Customize Toolbar\u{2026}")
                .build(app)?,
        ])
        .build()?;

    // ── Window menu ──────────────────────────────────────────────────

    let window_menu = SubmenuBuilder::new(app, "Window")
        .items(&[
            &PredefinedMenuItem::minimize(app, Some("Minimize"))?,
            &MenuItemBuilder::with_id("zoom_window", "Zoom")
                .build(app)?,
            &PredefinedMenuItem::separator(app)?,
            &PredefinedMenuItem::fullscreen(app, Some("Enter Full Screen"))?,
            &PredefinedMenuItem::separator(app)?,
            &MenuItemBuilder::with_id("bring_all_front", "Bring All to Front")
                .build(app)?,
        ])
        .build()?;

    // ── Help menu ────────────────────────────────────────────────────

    let help_menu = SubmenuBuilder::new(app, "Help")
        .items(&[
            &MenuItemBuilder::with_id("keyboard_shortcuts", "Keyboard Shortcuts")
                .accelerator("CmdOrCtrl+/")
                .build(app)?,
            &PredefinedMenuItem::separator(app)?,
            &MenuItemBuilder::with_id("documentation", "Documentation")
                .build(app)?,
            &MenuItemBuilder::with_id("website", "Inspekt Website")
                .build(app)?,
        ])
        .build()?;

    // ── Assemble ─────────────────────────────────────────────────────

    #[cfg(target_os = "macos")]
    {
        let app_menu = SubmenuBuilder::new(app, "Inspekt Browser VM")
            .items(&[
                &PredefinedMenuItem::about(
                    app,
                    Some("About Inspekt Browser VM"),
                    Some(
                        AboutMetadataBuilder::new()
                            .name(Some("Inspekt Browser VM"))
                            .version(Some("0.1.0"))
                            .copyright(Some("\u{00a9} 2026 Eleven Ways"))
                            .website(Some("https://inspekt.dev"))
                            .website_label(Some("Visit Inspekt"))
                            .build(),
                    ),
                )?,
                &PredefinedMenuItem::separator(app)?,
                &MenuItemBuilder::with_id("settings", "Settings\u{2026}")
                    .accelerator("CmdOrCtrl+,")
                    .build(app)?,
                &PredefinedMenuItem::separator(app)?,
                &PredefinedMenuItem::services(app, Some("Services"))?,
                &PredefinedMenuItem::separator(app)?,
                &PredefinedMenuItem::hide(app, Some("Hide Inspekt Browser VM"))?,
                &PredefinedMenuItem::hide_others(app, Some("Hide Others"))?,
                &PredefinedMenuItem::show_all(app, Some("Show All"))?,
                &PredefinedMenuItem::separator(app)?,
                &PredefinedMenuItem::quit(app, Some("Quit Inspekt Browser VM"))?,
            ])
            .build()?;

        MenuBuilder::new(app)
            .items(&[
                &app_menu,
                &file_menu,
                &edit_menu,
                &view_menu,
                &navigate_menu,
                &tools_menu,
                &vm_menu,
                &window_menu,
                &help_menu,
            ])
            .build()
    }

    #[cfg(not(target_os = "macos"))]
    {
        MenuBuilder::new(app)
            .items(&[
                &file_menu,
                &edit_menu,
                &view_menu,
                &navigate_menu,
                &tools_menu,
                &vm_menu,
                &window_menu,
                &help_menu,
            ])
            .build()
    }
}
