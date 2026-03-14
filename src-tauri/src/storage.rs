//! Chats storage location: config file and get/set path commands.

use std::fs;
use std::path::PathBuf;

use crate::chat_log::ChatLogState;

/// Path to the config file that stores the custom chats directory.
pub fn chats_config_path() -> PathBuf {
    std::env::current_exe()
        .ok()
        .and_then(|p| p.parent().map(|d| d.join("jarvis-chats-dir.txt")))
        .unwrap_or_else(|| PathBuf::from("jarvis-chats-dir.txt"))
}

/// Directory where chat logs are stored. Reads from config file if set, else default (cwd/chats).
pub fn chats_dir() -> Result<PathBuf, String> {
    let config_path = chats_config_path();
    if config_path.exists() {
        if let Ok(s) = fs::read_to_string(&config_path) {
            let s = s.trim();
            if !s.is_empty() {
                let p = PathBuf::from(s);
                if p.is_dir() || !p.exists() {
                    return Ok(p);
                }
            }
        }
    }
    std::env::current_dir()
        .map_err(|e| e.to_string())
        .map(|d| d.join("chats"))
}

#[tauri::command]
pub fn get_chats_storage_path() -> Result<String, String> {
    chats_dir().map(|p| p.to_string_lossy().into_owned())
}

#[tauri::command]
pub fn set_chats_storage_path(state: tauri::State<ChatLogState>, path: String) -> Result<(), String> {
    let path = path.trim();
    if path.is_empty() {
        return Err("Path cannot be empty.".to_string());
    }
    let config_path = chats_config_path();
    if let Some(parent) = config_path.parent() {
        std::fs::create_dir_all(parent).map_err(|e| e.to_string())?;
    }
    std::fs::write(&config_path, path).map_err(|e| e.to_string())?;
    *state.current_path.lock().map_err(|e| e.to_string())? = None;
    Ok(())
}
