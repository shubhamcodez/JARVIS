// Prevents additional console window on Windows in release
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

/// Runs a single binary operation. Returns the result or an error string (e.g. divide by zero).
#[tauri::command]
fn calculate(a: f64, b: f64, op: &str) -> Result<f64, String> {
    let result = match op {
        "+" => a + b,
        "-" => a - b,
        "*" => a * b,
        "/" => {
            if b == 0.0 {
                return Err("Error".to_string());
            }
            a / b
        }
        "%" => {
            if b == 0.0 {
                return Err("Error".to_string());
            }
            a % b
        }
        _ => return Err("Unknown operation".to_string()),
    };
    Ok(result)
}

fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .invoke_handler(tauri::generate_handler![calculate])
        .run(tauri::generate_context!())
        .expect("error while running Tauri application");
}
