//! Chat log state and commands: append messages, list chat history.

use std::fs::{self, OpenOptions};
use std::io::{Read, Write};
use std::path::PathBuf;
use std::sync::Mutex;

use crate::storage;

/// In-memory state for the current chat session (path to the active log file).
#[derive(Default)]
pub struct ChatLogState {
    pub current_path: Mutex<Option<PathBuf>>,
}

#[tauri::command]
pub fn append_chat_log(
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
        let dir = storage::chats_dir()?;
        std::fs::create_dir_all(&dir).map_err(|e| e.to_string())?;
        let ts = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .map_err(|e| e.to_string())?
            .as_secs();
        *path_guard = Some(dir.join(format!("{}.txt", ts)));
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
                format!(
                    "{}…",
                    title.chars().take(CHAT_TITLE_MAX_LEN).collect::<String>()
                )
            } else {
                title.to_string()
            };
        }
    }
    "New chat".to_string()
}

#[derive(serde::Serialize)]
pub struct ChatEntry {
    pub id: String,
    pub title: String,
}

#[tauri::command]
pub fn list_chats() -> Result<Vec<ChatEntry>, String> {
    let dir = storage::chats_dir()?;
    if !dir.is_dir() {
        return Ok(Vec::new());
    }
    let mut entries: Vec<ChatEntry> = fs::read_dir(&dir)
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
