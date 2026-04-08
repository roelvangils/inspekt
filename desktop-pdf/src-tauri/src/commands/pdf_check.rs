//! PDF checking commands.
//!
//! Runs the inspekt CLI to check PDF accessibility and streams progress.

use serde::{Deserialize, Serialize};
use std::fs::File;
use std::io::Read;
use std::path::Path;
use std::process::Stdio;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;
use std::time::Instant;
use tauri::{AppHandle, Emitter};
use tokio::io::{AsyncBufReadExt, BufReader};
use tokio::process::Command;
use tokio::sync::Mutex;
use zip::ZipArchive;

/// Global flag to cancel the current check.
static CANCEL_FLAG: AtomicBool = AtomicBool::new(false);

// =============================================================================
// JSON Progress Event Types (matching Python structured_progress.py)
// =============================================================================

/// Result from quick PDF pre-scan for timing estimation.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PrescanResult {
    pub file_size_bytes: u64,
    pub page_count: u32,
    pub estimated_image_count: u32,
    pub has_text_layer: bool,
    pub is_encrypted: bool,
    pub has_structure_tree: bool,
    pub file_complexity: String,
    #[serde(default)]
    pub sample_pages_analyzed: u32,
    #[serde(default)]
    pub has_forms: bool,
    #[serde(default)]
    pub has_annotations: bool,
}

/// Timing information for a substep within a main step.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SubstepTiming {
    pub substep_id: String,
    pub label: String,
    pub estimated_ms: u64,
}

/// Timing information for a main progress step.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct StepTiming {
    pub step_id: String,
    pub label: String,
    pub estimated_ms: u64,
    pub will_run: bool,
    #[serde(default)]
    pub substeps: Vec<SubstepTiming>,
}

/// Complete timing estimate for all steps.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TimingEstimate {
    pub total_estimated_ms: u64,
    pub steps: Vec<StepTiming>,
}

/// Progress event from Python CLI (parsed from stderr JSON).
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ProgressEvent {
    pub event_type: String,
    pub timestamp_ms: u64,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub step_id: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub substep_id: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub label: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub note: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub progress_percent: Option<u32>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub current: Option<u32>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub total: Option<u32>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub prescan_result: Option<PrescanResult>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub timing_estimate: Option<TimingEstimate>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub total_time_ms: Option<u64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub error_message: Option<String>,
}

// =============================================================================
// Tauri Event Types (emitted to frontend)
// =============================================================================

/// Legacy progress update (for backwards compatibility).
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CheckProgress {
    pub step: String,
    pub percentage: u32,
}

/// Enhanced progress event emitted to frontend.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CheckProgressEvent {
    pub event_type: String,
    pub timestamp_ms: u64,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub step_id: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub substep_id: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub label: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub note: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub progress_percent: Option<u32>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub current: Option<u32>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub total: Option<u32>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub prescan_result: Option<PrescanResult>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub timing_estimate: Option<TimingEstimate>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub total_time_ms: Option<u64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub error_message: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub estimated_remaining_ms: Option<u64>,
}

impl From<ProgressEvent> for CheckProgressEvent {
    fn from(event: ProgressEvent) -> Self {
        CheckProgressEvent {
            event_type: event.event_type,
            timestamp_ms: event.timestamp_ms,
            step_id: event.step_id,
            substep_id: event.substep_id,
            label: event.label,
            note: event.note,
            progress_percent: event.progress_percent,
            current: event.current,
            total: event.total,
            prescan_result: event.prescan_result,
            timing_estimate: event.timing_estimate,
            total_time_ms: event.total_time_ms,
            error_message: event.error_message,
            estimated_remaining_ms: None,
        }
    }
}

/// Result of a PDF check operation.
#[derive(Debug, Serialize, Deserialize)]
pub struct CheckResult {
    pub success: bool,
    pub report: Option<serde_json::Value>,
    pub error: Option<String>,
}

// =============================================================================
// Progress Tracking State
// =============================================================================

/// Tracks progress state for ETA calculation.
#[derive(Debug)]
struct ProgressState {
    start_time: Instant,
    timing_estimate: Option<TimingEstimate>,
    completed_steps: Vec<String>,
    current_step: Option<String>,
    current_step_progress: u32,
}

impl ProgressState {
    fn new() -> Self {
        ProgressState {
            start_time: Instant::now(),
            timing_estimate: None,
            completed_steps: Vec::new(),
            current_step: None,
            current_step_progress: 0,
        }
    }

    fn set_timing(&mut self, timing: TimingEstimate) {
        self.timing_estimate = Some(timing);
    }

    fn step_started(&mut self, step_id: &str) {
        self.current_step = Some(step_id.to_string());
        self.current_step_progress = 0;
    }

    fn step_ended(&mut self, step_id: &str) {
        self.completed_steps.push(step_id.to_string());
        if self.current_step.as_deref() == Some(step_id) {
            self.current_step = None;
            self.current_step_progress = 0;
        }
    }

    fn update_progress(&mut self, percent: u32) {
        self.current_step_progress = percent;
    }

    /// Calculate estimated remaining time in milliseconds.
    fn calculate_remaining_ms(&self) -> Option<u64> {
        let timing = self.timing_estimate.as_ref()?;

        let elapsed_ms = self.start_time.elapsed().as_millis() as u64;

        // Calculate completed time from finished steps
        let mut completed_ms: u64 = 0;
        for step_id in &self.completed_steps {
            if let Some(step) = timing.steps.iter().find(|s| &s.step_id == step_id) {
                completed_ms += step.estimated_ms;
            }
        }

        // Add partial progress of current step
        if let Some(ref current_step_id) = self.current_step {
            if let Some(step) = timing.steps.iter().find(|s| &s.step_id == current_step_id) {
                let step_progress = self.current_step_progress as u64;
                completed_ms += (step.estimated_ms * step_progress) / 100;
            }
        }

        // Estimate remaining based on ratio
        let total_estimated = timing.total_estimated_ms;
        if completed_ms >= total_estimated {
            return Some(0);
        }

        // Use actual elapsed time to calibrate estimate
        let remaining_estimated = total_estimated - completed_ms;

        // If we have enough elapsed time, adjust based on actual pace
        if elapsed_ms > 1000 && completed_ms > 0 {
            let pace_ratio = elapsed_ms as f64 / completed_ms as f64;
            let adjusted_remaining = (remaining_estimated as f64 * pace_ratio) as u64;
            // Blend estimated and adjusted (70% adjusted, 30% estimated)
            Some((adjusted_remaining * 7 + remaining_estimated * 3) / 10)
        } else {
            Some(remaining_estimated)
        }
    }
}

// =============================================================================
// Commands
// =============================================================================

/// Run inspekt pdf check on a PDF file.
///
/// This command spawns the inspekt CLI as a subprocess and streams
/// progress updates to the frontend via Tauri events.
///
/// # Arguments
/// * `app` - Tauri app handle for emitting events
/// * `path` - Path to the PDF file to check
/// * `engine` - Check engine to use ("basic", "simple", "vera", "all")
/// * `with_preview` - Whether to generate interactive preview data (page images, tag overlays)
///
/// # Returns
/// * `Ok(CheckResult)` - Result with parsed report JSON
/// * `Err(String)` - Error message if check fails
#[tauri::command]
pub async fn check_pdf(
    app: AppHandle,
    path: String,
    engine: String,
    with_preview: Option<bool>,
) -> Result<CheckResult, String> {
    // Reset cancel flag
    CANCEL_FLAG.store(false, Ordering::SeqCst);

    // Emit initial progress (legacy format for backwards compatibility)
    let _ = app.emit(
        "check-progress",
        CheckProgress {
            step: "Starting PDF check...".to_string(),
            percentage: 0,
        },
    );

    // Also emit new format
    let _ = app.emit(
        "check-progress-v2",
        CheckProgressEvent {
            event_type: "init".to_string(),
            timestamp_ms: 0,
            step_id: None,
            substep_id: None,
            label: Some("Starting PDF check...".to_string()),
            note: None,
            progress_percent: Some(0),
            current: None,
            total: None,
            prescan_result: None,
            timing_estimate: None,
            total_time_ms: None,
            error_message: None,
            estimated_remaining_ms: None,
        },
    );

    // Create temporary paths for output
    let temp_dir = std::env::temp_dir();
    let use_pdfi = with_preview.unwrap_or(false);

    let (output_path, is_pdfi) = if use_pdfi {
        let pdfi_path = temp_dir.join(format!("inspekt_report_{}.pdfi", std::process::id()));
        (pdfi_path, true)
    } else {
        let json_path = temp_dir.join(format!("inspekt_report_{}.json", std::process::id()));
        (json_path, false)
    };
    let output_str = output_path.to_string_lossy().to_string();

    // Build command with --structured-progress flag for JSON events
    let mut cmd = Command::new("inspekt");
    cmd.arg("pdf")
        .arg("check")
        .arg(&path)
        .arg("--engine")
        .arg(&engine)
        .arg("--structured-progress"); // Enable JSON progress events

    if is_pdfi {
        cmd.arg("--pdfi")
            .arg(&output_str)
            .arg("--interactive-pages")
            .arg("0");
    } else {
        cmd.arg("--json-output").arg(&output_str);
    }

    cmd.stdout(Stdio::piped()).stderr(Stdio::piped());

    // Spawn the process
    let mut child = cmd.spawn().map_err(|e| {
        if e.kind() == std::io::ErrorKind::NotFound {
            "Inspekt CLI not found. Please install it with: pip install inspekt".to_string()
        } else {
            format!("Failed to start inspekt: {}", e)
        }
    })?;

    let stdout = child.stdout.take();

    // Emit progress: process started
    let _ = app.emit(
        "check-progress",
        CheckProgress {
            step: "Analyzing PDF structure...".to_string(),
            percentage: 10,
        },
    );

    // Set up progress state for ETA calculation
    let progress_state = Arc::new(Mutex::new(ProgressState::new()));

    // Read stderr for progress (inspekt outputs progress to stderr)
    let stderr = child.stderr.take();
    let app_clone = app.clone();
    let progress_state_clone = progress_state.clone();

    if let Some(stderr) = stderr {
        let reader = BufReader::new(stderr);
        let mut lines = reader.lines();

        tokio::spawn(async move {
            while let Ok(Some(line)) = lines.next_line().await {
                if CANCEL_FLAG.load(Ordering::SeqCst) {
                    break;
                }

                let trimmed = line.trim();
                if trimmed.is_empty() {
                    continue;
                }

                // Try to parse as JSON progress event (new format)
                if let Ok(event) = serde_json::from_str::<ProgressEvent>(trimmed) {
                    // Update progress state
                    let mut state = progress_state_clone.lock().await;

                    match event.event_type.as_str() {
                        "prescan" => {
                            if let Some(ref timing) = event.timing_estimate {
                                state.set_timing(timing.clone());
                            }
                        }
                        "step_start" => {
                            if let Some(ref step_id) = event.step_id {
                                state.step_started(step_id);
                            }
                        }
                        "step_end" => {
                            if let Some(ref step_id) = event.step_id {
                                state.step_ended(step_id);
                            }
                        }
                        "step_progress" => {
                            if let Some(percent) = event.progress_percent {
                                state.update_progress(percent);
                            }
                        }
                        _ => {}
                    }

                    // Calculate estimated remaining time
                    let remaining = state.calculate_remaining_ms();
                    drop(state); // Release lock before emitting

                    // Convert to enhanced event with ETA
                    let mut check_event: CheckProgressEvent = event.clone().into();
                    check_event.estimated_remaining_ms = remaining;

                    // Emit new format event
                    let _ = app_clone.emit("check-progress-v2", check_event);

                    // Also emit legacy format for backwards compatibility
                    let legacy_step = event.label.unwrap_or_else(|| {
                        event
                            .step_id
                            .clone()
                            .unwrap_or_else(|| "Processing...".to_string())
                    });
                    let legacy_pct = event.progress_percent.unwrap_or(50);
                    let _ = app_clone.emit(
                        "check-progress",
                        CheckProgress {
                            step: legacy_step,
                            percentage: legacy_pct,
                        },
                    );
                } else {
                    // Fallback to legacy keyword matching for non-JSON output
                    let is_step_line = trimmed.contains("Run ")
                        || trimmed.contains("Create ")
                        || trimmed.contains("Analyze ")
                        || trimmed.contains("Extract ")
                        || trimmed.contains("Generate ")
                        || trimmed.contains("Classify ")
                        || trimmed.contains("Build ")
                        || trimmed.contains("Save ")
                        || trimmed.contains("Export ")
                        || trimmed.contains("Load ")
                        || trimmed.contains("checks")
                        || trimmed.contains("OCR")
                        || trimmed.contains("contrast")
                        || trimmed.contains("structure")
                        || trimmed.contains("thumbnail")
                        || trimmed.contains("report");

                    if is_step_line {
                        let clean_step = trimmed
                            .replace('\u{F043E}', "")
                            .replace('\u{F0130}', "")
                            .replace('\u{F012C}', "")
                            .trim()
                            .to_string();

                        let _ = app_clone.emit(
                            "check-progress",
                            CheckProgress {
                                step: clean_step,
                                percentage: 50,
                            },
                        );
                    }
                }
            }
        });
    }

    // Check for cancellation periodically while waiting
    let cancel_flag = Arc::new(AtomicBool::new(false));
    let cancel_clone = cancel_flag.clone();

    let output_future = async {
        loop {
            if CANCEL_FLAG.load(Ordering::SeqCst) {
                let _ = child.kill().await;
                cancel_clone.store(true, Ordering::SeqCst);
                return Err("Check cancelled by user".to_string());
            }

            match tokio::time::timeout(std::time::Duration::from_millis(100), child.wait()).await {
                Ok(result) => {
                    return result.map_err(|e| format!("Process error: {}", e));
                }
                Err(_) => {
                    continue;
                }
            }
        }
    };

    let status = output_future.await?;

    if cancel_flag.load(Ordering::SeqCst) {
        return Err("Check cancelled by user".to_string());
    }

    // Emit progress: almost done
    let _ = app.emit(
        "check-progress",
        CheckProgress {
            step: "Processing results...".to_string(),
            percentage: 90,
        },
    );

    // Read any stdout output for error messages
    let stdout_output = if let Some(mut stdout) = stdout {
        let mut buffer = Vec::new();
        tokio::io::AsyncReadExt::read_to_end(&mut stdout, &mut buffer)
            .await
            .map_err(|e| format!("Failed to read output: {}", e))?;
        String::from_utf8_lossy(&buffer).to_string()
    } else {
        String::new()
    };

    // Try to read the report from the output file
    let output = if is_pdfi {
        match extract_report_from_pdfi(&output_path) {
            Ok(content) => content,
            Err(e) => {
                let _ = std::fs::remove_file(&output_path);
                return Ok(CheckResult {
                    success: false,
                    report: None,
                    error: Some(format!(
                        "Failed to extract report from PDFI: {}. Inspekt exit code: {}",
                        e,
                        status.code().unwrap_or(-1)
                    )),
                });
            }
        }
    } else {
        match tokio::fs::read_to_string(&output_path).await {
            Ok(content) => content,
            Err(_e) => {
                return Ok(CheckResult {
                    success: false,
                    report: None,
                    error: Some(format!(
                        "Inspekt exited with code {}. No report generated. Output: {}",
                        status.code().unwrap_or(-1),
                        stdout_output.chars().take(500).collect::<String>()
                    )),
                });
            }
        }
    };

    let _ = std::fs::remove_file(&output_path);

    let report: serde_json::Value = serde_json::from_str(&output).map_err(|e| {
        format!(
            "Invalid JSON output: {}. First 200 chars: {}",
            e,
            &output.chars().take(200).collect::<String>()
        )
    })?;

    // Emit final progress events
    let _ = app.emit(
        "check-progress",
        CheckProgress {
            step: "Build report".to_string(),
            percentage: 80,
        },
    );
    let _ = app.emit(
        "check-progress",
        CheckProgress {
            step: "Save report".to_string(),
            percentage: 95,
        },
    );
    let _ = app.emit(
        "check-progress",
        CheckProgress {
            step: "Complete!".to_string(),
            percentage: 100,
        },
    );

    // Emit v2 complete event
    let elapsed_ms = progress_state.lock().await.start_time.elapsed().as_millis() as u64;
    let _ = app.emit(
        "check-progress-v2",
        CheckProgressEvent {
            event_type: "complete".to_string(),
            timestamp_ms: elapsed_ms,
            step_id: None,
            substep_id: None,
            label: Some("Complete!".to_string()),
            note: None,
            progress_percent: Some(100),
            current: None,
            total: None,
            prescan_result: None,
            timing_estimate: None,
            total_time_ms: Some(elapsed_ms),
            error_message: None,
            estimated_remaining_ms: Some(0),
        },
    );

    Ok(CheckResult {
        success: true,
        report: Some(report),
        error: None,
    })
}

/// Cancel the current PDF check operation.
#[tauri::command]
pub fn cancel_check() {
    CANCEL_FLAG.store(true, Ordering::SeqCst);
}

/// Extract the report.json content from a PDFI package (ZIP archive).
fn extract_report_from_pdfi(pdfi_path: &Path) -> Result<String, String> {
    let file =
        File::open(pdfi_path).map_err(|e| format!("Failed to open PDFI package: {}", e))?;

    let mut archive =
        ZipArchive::new(file).map_err(|e| format!("Failed to read PDFI as ZIP: {}", e))?;

    let mut report_file = archive
        .by_name("report.json")
        .map_err(|_| "PDFI package does not contain report.json".to_string())?;

    let mut content = String::new();
    report_file
        .read_to_string(&mut content)
        .map_err(|e| format!("Failed to read report.json: {}", e))?;

    Ok(content)
}
