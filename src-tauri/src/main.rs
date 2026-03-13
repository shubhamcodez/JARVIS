// Prevents additional console window on Windows in release
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use reqwest::Client;
use serde::{Deserialize, Serialize};

#[derive(Debug, Serialize)]
struct ChatRequest {
    model: String,
    messages: Vec<ChatMessage>,
}

#[derive(Debug, Serialize, Deserialize)]
struct ChatMessage {
    role: String,
    content: String,
}

#[derive(Debug, Deserialize)]
struct ChatResponse {
    choices: Vec<ChatChoice>,
}

#[derive(Debug, Deserialize)]
struct ChatChoice {
    message: ChatMessage,
}

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
async fn chatbot_response(message: String) -> Result<String, String> {
    load_env();
    let api_key = std::env::var("OPENAI_API_KEY")
        .map_err(|_| "OPENAI_API_KEY not set. Add it to a .env file in the project root.")?;

    let client = Client::new();
    let body = ChatRequest {
        model: "gpt-4o-mini".to_string(),
        messages: vec![ChatMessage {
            role: "user".to_string(),
            content: message,
        }],
    };

    let res = client
        .post("https://api.openai.com/v1/chat/completions")
        .bearer_auth(api_key)
        .json(&body)
        .send()
        .await
        .map_err(|e| e.to_string())?;

    if !res.status().is_success() {
        let status = res.status();
        let text = res.text().await.unwrap_or_default();
        return Err(format!("API error {}: {}", status, text));
    }

    let chat: ChatResponse = res.json().await.map_err(|e| e.to_string())?;
    let reply = chat
        .choices
        .into_iter()
        .next()
        .map(|c| c.message.content)
        .unwrap_or_else(|| "No response.".to_string());

    Ok(reply)
}

fn main() {
    load_env();

    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .invoke_handler(tauri::generate_handler![chatbot_response])
        .run(tauri::generate_context!())
        .expect("error while running Tauri application");
}
