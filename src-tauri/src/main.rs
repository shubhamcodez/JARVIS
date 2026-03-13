// Prevents additional console window on Windows in release
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod openai;

use std::fs::{self, OpenOptions};
use std::io::{Read, Write};
use std::path::PathBuf;
use std::sync::Mutex;

/// Load .env from current dir, parent, or next to the executable.
fn load_env() {
    let _ = dotenvy::dotenv();
    if std::env::var("OPENAI_API_KEY").is_err() {
        let _ = dotenvy::from_path("../.env");
    }
    if std::env::var("OPENAI_API_KEY").is_err() {
        if let Ok(exe) = std::env::current_exe() {
            if let Some(dir) = exe.parent() {
                let _ = dotenvy::from_path(dir.join(".env"));
            }
        }
    }
}

#[tauri::command]
fn window_minimize(window: tauri::Window) {
    let _ = window.minimize();
}

#[tauri::command]
fn window_close(window: tauri::Window) {
    let _ = window.close();
}

#[tauri::command]
fn window_toggle_maximize(window: tauri::Window) {
    if window.is_maximized().unwrap_or(false) {
        let _ = window.unmaximize();
    } else {
        let _ = window.maximize();
    }
}

/// Root directory for app data (chats/). Uses current working directory.
fn root_dir() -> Result<PathBuf, String> {
    std::env::current_dir().map_err(|e| e.to_string())
}

#[derive(Default)]
struct ChatLogState {
    current_path: Mutex<Option<PathBuf>>,
}

#[tauri::command]
fn append_chat_log(
    state: tauri::State<ChatLogState>,
    role: String,
    content: String,
) -> Result<(), String> {
    let prefix = match role.as_str() {
        "user" => "user:",
        "assistant" => "assistant:",
        _ => return Err("role must be 'user' or 'assistant'".to_string()),
    };

    let mut path_guard = state.current_path.lock().map_err(|e| e.to_string())?;

    if path_guard.is_none() {
        let root = root_dir()?;
        let chats_dir = root.join("chats");
        std::fs::create_dir_all(&chats_dir).map_err(|e| e.to_string())?;
        let ts = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .map_err(|e| e.to_string())?
            .as_secs();
        *path_guard = Some(chats_dir.join(format!("{}.txt", ts)));
    }

    let path = path_guard.as_ref().unwrap();
    let mut f = OpenOptions::new()
        .create(true)
        .append(true)
        .open(path)
        .map_err(|e| e.to_string())?;

    writeln!(f, "{} {}", prefix, content.trim_end().replace("\n", "\n  "))
        .map_err(|e| e.to_string())?;

    Ok(())
}

const CHAT_TITLE_MAX_LEN: usize = 48;

fn title_from_log_path(path: &std::path::Path) -> String {
    let mut f = match fs::File::open(path) {
        Ok(f) => f,
        Err(_) => return "New chat".to_string(),
    };
    let mut buf = [0u8; 1024];
    let n = f.read(&mut buf).unwrap_or(0);
    let s = String::from_utf8_lossy(&buf[..n]);
    for line in s.lines() {
        let line = line.trim_start();
        if let Some(after) = line.strip_prefix("user:") {
            let title = after.trim();
            if title.is_empty() {
                return "New chat".to_string();
            }
            return if title.len() > CHAT_TITLE_MAX_LEN {
                format!("{}…", title.chars().take(CHAT_TITLE_MAX_LEN).collect::<String>())
            } else {
                title.to_string()
            };
        }
    }
    "New chat".to_string()
}

#[derive(serde::Serialize)]
struct ChatEntry {
    id: String,
    title: String,
}

#[tauri::command]
fn list_chats() -> Result<Vec<ChatEntry>, String> {
    let root = root_dir()?;
    let chats_dir = root.join("chats");
    if !chats_dir.is_dir() {
        return Ok(Vec::new());
    }
    let mut entries: Vec<ChatEntry> = fs::read_dir(&chats_dir)
        .map_err(|e| e.to_string())?
        .filter_map(|e| e.ok())
        .filter_map(|e| {
            let p = e.path();
            if p.extension().and_then(|x| x.to_str()) != Some("txt") {
                return None;
            }
            let id = p.file_stem().and_then(|s| s.to_str())?.to_string();
            let title = title_from_log_path(&p);
            Some(ChatEntry { id, title })
        })
        .collect();
    entries.sort_by(|a, b| b.id.cmp(&a.id));
    Ok(entries)
}

#[tauri::command]
async fn open_file_picker(app: tauri::AppHandle) -> Result<Vec<String>, String> {
    use tauri_plugin_dialog::DialogExt;
    let paths = tauri::async_runtime::spawn_blocking(move || {
        app.dialog().file().blocking_pick_files()
    })
    .await
    .map_err(|e| e.to_string())?
    .unwrap_or_default();
    let strings: Vec<String> = paths
        .into_iter()
        .map(|p| p.to_string())
        .collect();
    Ok(strings)
}

#[tauri::command]
async fn chatbot_response(
    message: String,
    attachment_paths: Option<Vec<String>>,
) -> Result<String, String> {
    load_env();
    let api_key = std::env::var("OPENAI_API_KEY")
        .map_err(|_| "OPENAI_API_KEY not set. Add it to a .env file in the project root.")?;
    openai::chat(&api_key, message, attachment_paths).await
}

fn main() {
    load_env();

    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_shell::init())
        .manage(ChatLogState::default())
        .invoke_handler(tauri::generate_handler![
            chatbot_response,
            window_minimize,
            window_close,
            window_toggle_maximize,
            append_chat_log,
            list_chats,
            open_file_picker,
        ])
        .plugin(tauri_plugin_dialog::init())
        .run(tauri::generate_context!())
        .expect("error while running Tauri application");
}
