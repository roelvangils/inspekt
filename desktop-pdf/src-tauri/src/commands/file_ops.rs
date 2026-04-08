//! File operation commands.
//!
//! Handles reading and parsing JSON report files and PDFI packages.

use serde::{Deserialize, Serialize};
use std::fs::{self, File};
use std::io::{Read, Write};
use std::path::Path;
use zip::write::SimpleFileOptions;
use zip::{ZipArchive, ZipWriter};

/// File information returned to the frontend.
#[derive(Debug, Serialize, Deserialize)]
pub struct FileInfo {
    pub path: String,
    pub name: String,
    pub extension: String,
    pub size: u64,
    pub is_json: bool,
    pub is_pdf: bool,
}

/// Read and parse a JSON file.
///
/// # Arguments
/// * `path` - Path to the JSON file
///
/// # Returns
/// * `Ok(serde_json::Value)` - Parsed JSON content
/// * `Err(String)` - Error message if reading or parsing fails
#[tauri::command]
pub async fn read_json_file(path: String) -> Result<serde_json::Value, String> {
    let file_path = Path::new(&path);

    // Check if file exists
    if !file_path.exists() {
        return Err(format!("File not found: {}", path));
    }

    // Check file extension
    let extension = file_path
        .extension()
        .and_then(|e| e.to_str())
        .unwrap_or("");

    if extension.to_lowercase() != "json" {
        return Err(format!("Expected JSON file, got .{}", extension));
    }

    // Read file content
    let content = fs::read_to_string(file_path)
        .map_err(|e| format!("Failed to read file: {}", e))?;

    // Parse JSON
    let json: serde_json::Value = serde_json::from_str(&content)
        .map_err(|e| format!("Invalid JSON: {}", e))?;

    Ok(json)
}

/// Get file information without reading the entire file.
///
/// # Arguments
/// * `path` - Path to the file
///
/// # Returns
/// * `Ok(FileInfo)` - File metadata
/// * `Err(String)` - Error message if file cannot be accessed
#[tauri::command]
pub async fn get_file_info(path: String) -> Result<FileInfo, String> {
    let file_path = Path::new(&path);

    // Check if file exists
    if !file_path.exists() {
        return Err(format!("File not found: {}", path));
    }

    // Get file metadata
    let metadata = fs::metadata(file_path)
        .map_err(|e| format!("Failed to read file metadata: {}", e))?;

    let name = file_path
        .file_name()
        .and_then(|n| n.to_str())
        .unwrap_or("unknown")
        .to_string();

    let extension = file_path
        .extension()
        .and_then(|e| e.to_str())
        .unwrap_or("")
        .to_lowercase();

    Ok(FileInfo {
        path,
        name,
        is_json: extension == "json",
        is_pdf: extension == "pdf",
        extension,
        size: metadata.len(),
    })
}

/// Extract a .pdfi package (ZIP archive) to a temporary directory.
///
/// PDFI packages are self-contained bundles containing:
/// - report.json: The accessibility report data
/// - source.pdf: The original PDF file
/// - manifest.json: Package metadata
/// - assets/: Directory containing page images, thumbnails, and screenshots
///
/// # Arguments
/// * `path` - Path to the .pdfi package file
///
/// # Returns
/// * `Ok(String)` - Path to the extraction directory
/// * `Err(String)` - Error message if extraction fails
#[tauri::command]
pub async fn extract_pdfi_package(path: String) -> Result<String, String> {
    let package_path = Path::new(&path);

    // Check if file exists
    if !package_path.exists() {
        return Err(format!("File not found: {}", path));
    }

    // Check file extension
    let extension = package_path
        .extension()
        .and_then(|e| e.to_str())
        .unwrap_or("");

    if extension.to_lowercase() != "pdfi" {
        return Err(format!("Expected .pdfi file, got .{}", extension));
    }

    // Open the ZIP archive
    let file = File::open(package_path)
        .map_err(|e| format!("Failed to open package: {}", e))?;

    let mut archive = ZipArchive::new(file)
        .map_err(|e| format!("Failed to read package as ZIP: {}", e))?;

    // Create extraction directory in temp with a unique name based on the package
    let file_stem = package_path
        .file_stem()
        .and_then(|s| s.to_str())
        .unwrap_or("pdfi_package");

    // Use a hash-like approach for unique directory names
    let extract_dir = std::env::temp_dir()
        .join("inspekt-pdfi")
        .join(format!("{}_{}", file_stem, std::process::id()));

    // Create the extraction directory
    fs::create_dir_all(&extract_dir)
        .map_err(|e| format!("Failed to create extraction directory: {}", e))?;

    // Extract all files
    for i in 0..archive.len() {
        let mut file = archive.by_index(i)
            .map_err(|e| format!("Failed to access file in archive: {}", e))?;

        let outpath = match file.enclosed_name() {
            Some(path) => extract_dir.join(path),
            None => continue, // Skip files with unsafe paths
        };

        // Create parent directories if needed
        if let Some(parent) = outpath.parent() {
            if !parent.exists() {
                fs::create_dir_all(parent)
                    .map_err(|e| format!("Failed to create directory: {}", e))?;
            }
        }

        // Extract file or directory
        if file.is_dir() {
            fs::create_dir_all(&outpath)
                .map_err(|e| format!("Failed to create directory: {}", e))?;
        } else {
            let mut outfile = File::create(&outpath)
                .map_err(|e| format!("Failed to create file: {}", e))?;

            let mut buffer = Vec::new();
            file.read_to_end(&mut buffer)
                .map_err(|e| format!("Failed to read from archive: {}", e))?;

            outfile.write_all(&buffer)
                .map_err(|e| format!("Failed to write file: {}", e))?;
        }
    }

    // Verify that report.json exists in the extracted package
    let report_path = extract_dir.join("report.json");
    if !report_path.exists() {
        // Clean up the extraction directory
        let _ = fs::remove_dir_all(&extract_dir);
        return Err("Invalid PDFI package: missing report.json".to_string());
    }

    Ok(extract_dir.to_string_lossy().to_string())
}

/// Clean up an extracted PDFI package directory.
///
/// # Arguments
/// * `path` - Path to the extraction directory to clean up
///
/// # Returns
/// * `Ok(())` - Directory was successfully removed
/// * `Err(String)` - Error message if cleanup fails
#[tauri::command]
pub async fn cleanup_pdfi_extraction(path: String) -> Result<(), String> {
    let dir_path = Path::new(&path);

    // Safety check: only allow cleanup of directories in our temp folder
    let temp_base = std::env::temp_dir().join("inspekt-pdfi");
    if !dir_path.starts_with(&temp_base) {
        return Err("Can only clean up PDFI extraction directories".to_string());
    }

    if dir_path.exists() {
        fs::remove_dir_all(dir_path)
            .map_err(|e| format!("Failed to clean up extraction directory: {}", e))?;
    }

    Ok(())
}

/// Save the current report as a .pdfi package (ZIP archive).
///
/// PDFI packages are self-contained bundles containing:
/// - manifest.json: Package metadata (version, created_at)
/// - report.json: The accessibility report data
/// - source.pdf: The original PDF file (if available)
/// - assets/: Directory containing page images, thumbnails, and screenshots
///
/// # Arguments
/// * `report_json` - The report data as a JSON string
/// * `source_pdf_path` - Path to the source PDF file (optional)
/// * `assets_path` - Path to the assets directory (optional)
/// * `output_path` - Path where the .pdfi package should be saved
///
/// # Returns
/// * `Ok(())` - Package was saved successfully
/// * `Err(String)` - Error message if saving fails
#[tauri::command]
pub async fn save_as_pdfi(
    report_json: String,
    source_pdf_path: Option<String>,
    assets_path: Option<String>,
    output_path: String,
) -> Result<(), String> {
    let output = Path::new(&output_path);

    // Create the ZIP file
    let file = File::create(output)
        .map_err(|e| format!("Failed to create output file: {}", e))?;

    let mut zip = ZipWriter::new(file);
    let options = SimpleFileOptions::default()
        .compression_method(zip::CompressionMethod::Deflated)
        .compression_level(Some(6));

    // 1. Write manifest.json
    let manifest = serde_json::json!({
        "version": "1.0",
        "created_at": chrono::Utc::now().to_rfc3339(),
        "generator": "Inspekt PDF Viewer",
    });
    let manifest_json = serde_json::to_string_pretty(&manifest)
        .map_err(|e| format!("Failed to serialize manifest: {}", e))?;

    zip.start_file("manifest.json", options)
        .map_err(|e| format!("Failed to add manifest.json to archive: {}", e))?;
    zip.write_all(manifest_json.as_bytes())
        .map_err(|e| format!("Failed to write manifest.json: {}", e))?;

    // 2. Write report.json (pretty-printed for readability)
    let report_value: serde_json::Value = serde_json::from_str(&report_json)
        .map_err(|e| format!("Invalid report JSON: {}", e))?;
    let pretty_report = serde_json::to_string_pretty(&report_value)
        .map_err(|e| format!("Failed to format report JSON: {}", e))?;

    zip.start_file("report.json", options)
        .map_err(|e| format!("Failed to add report.json to archive: {}", e))?;
    zip.write_all(pretty_report.as_bytes())
        .map_err(|e| format!("Failed to write report.json: {}", e))?;

    // 3. Copy source.pdf if available
    if let Some(pdf_path) = source_pdf_path {
        let pdf_file = Path::new(&pdf_path);
        if pdf_file.exists() {
            let mut pdf_content = Vec::new();
            let mut pdf_reader = File::open(pdf_file)
                .map_err(|e| format!("Failed to open source PDF: {}", e))?;
            pdf_reader.read_to_end(&mut pdf_content)
                .map_err(|e| format!("Failed to read source PDF: {}", e))?;

            zip.start_file("source.pdf", options)
                .map_err(|e| format!("Failed to add source.pdf to archive: {}", e))?;
            zip.write_all(&pdf_content)
                .map_err(|e| format!("Failed to write source.pdf: {}", e))?;
        }
    }

    // 4. Copy assets directory if available
    if let Some(assets_dir) = assets_path {
        let assets_path = Path::new(&assets_dir);
        if assets_path.exists() && assets_path.is_dir() {
            add_directory_to_zip(&mut zip, assets_path, "assets", options)?;
        }
    }

    // Finalize the ZIP archive
    zip.finish()
        .map_err(|e| format!("Failed to finalize archive: {}", e))?;

    Ok(())
}

/// Recursively add a directory and its contents to a ZIP archive.
fn add_directory_to_zip(
    zip: &mut ZipWriter<File>,
    source_dir: &Path,
    archive_prefix: &str,
    options: SimpleFileOptions,
) -> Result<(), String> {
    // Iterate over directory entries
    let entries = fs::read_dir(source_dir)
        .map_err(|e| format!("Failed to read directory {}: {}", source_dir.display(), e))?;

    for entry in entries {
        let entry = entry
            .map_err(|e| format!("Failed to read directory entry: {}", e))?;
        let path = entry.path();
        let file_name = entry.file_name();
        let file_name_str = file_name.to_string_lossy();
        let archive_path = format!("{}/{}", archive_prefix, file_name_str);

        if path.is_dir() {
            // Recursively add subdirectory
            add_directory_to_zip(zip, &path, &archive_path, options)?;
        } else if path.is_file() {
            // Add file to archive
            let mut file_content = Vec::new();
            let mut file_reader = File::open(&path)
                .map_err(|e| format!("Failed to open file {}: {}", path.display(), e))?;
            file_reader.read_to_end(&mut file_content)
                .map_err(|e| format!("Failed to read file {}: {}", path.display(), e))?;

            zip.start_file(&archive_path, options)
                .map_err(|e| format!("Failed to add {} to archive: {}", archive_path, e))?;
            zip.write_all(&file_content)
                .map_err(|e| format!("Failed to write {}: {}", archive_path, e))?;
        }
    }

    Ok(())
}
