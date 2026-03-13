//! OpenAI API client: file upload and chat completions.

use std::fs;
use reqwest::Client;
use serde::{Deserialize, Serialize};
use serde_json::Value as JsonValue;

#[derive(Debug, Serialize)]
struct ChatRequest {
    model: String,
    messages: Vec<ChatMessageRequest>,
}

#[derive(Debug, Serialize)]
struct ChatMessageRequest {
    role: String,
    content: JsonValue,
}

#[derive(Debug, Deserialize)]
struct ChatMessage {
    #[allow(dead_code)]
    role: String,
    content: String,
}

#[derive(Debug, Deserialize)]
struct OpenAIFileResponse {
    id: String,
}

#[derive(Debug, Deserialize)]
struct ChatResponse {
    choices: Vec<ChatChoice>,
}

#[derive(Debug, Deserialize)]
struct ChatChoice {
    message: ChatMessage,
}

fn path_for_reading(s: &str) -> &str {
    s.strip_prefix("file://").unwrap_or(s)
}

/// Upload a file to OpenAI Files API (purpose=user_data) for document/vision models.
/// Returns the file ID on success.
async fn upload_file(
    client: &Client,
    api_key: &str,
    path: &str,
) -> Result<String, String> {
    let path_clean = path_for_reading(path);
    let file_bytes = fs::read(path_clean).map_err(|e| format!("Read file: {}", e))?;
    let filename = std::path::Path::new(path_clean)
        .file_name()
        .and_then(|n| n.to_str())
        .unwrap_or("document");
    let part = reqwest::multipart::Part::bytes(file_bytes)
        .file_name(filename.to_string())
        .mime_str(
            mime_guess::from_path(path_clean)
                .first_raw()
                .unwrap_or("application/octet-stream"),
        )
        .map_err(|e| e.to_string())?;
    let form = reqwest::multipart::Form::new()
        .part("file", part)
        .text("purpose", "user_data");
    let res = client
        .post("https://api.openai.com/v1/files")
        .bearer_auth(api_key)
        .multipart(form)
        .send()
        .await
        .map_err(|e| e.to_string())?;
    if !res.status().is_success() {
        let status = res.status();
        let text = res.text().await.unwrap_or_default();
        return Err(format!("OpenAI file upload {}: {}", status, text));
    }
    let file_res: OpenAIFileResponse = res.json().await.map_err(|e| e.to_string())?;
    Ok(file_res.id)
}

#[allow(dead_code)]
fn read_attachment_paths(paths: &[String]) -> String {
    let mut parts = Vec::new();
    for path in paths {
        let path_clean = path_for_reading(path);
        if let Ok(content) = fs::read_to_string(path_clean) {
            let name = std::path::Path::new(path_clean)
                .file_name()
                .and_then(|n| n.to_str())
                .unwrap_or("file");
            parts.push(format!("[Contents of {}]\n{}", name, content));
        }
    }
    parts.join("\n\n")
}

/// Send a chat completion request, optionally with uploaded file attachments.
pub async fn chat(
    api_key: &str,
    message: String,
    attachment_paths: Option<Vec<String>>,
) -> Result<String, String> {
    let client = Client::new();

    let (user_content, model) = match attachment_paths {
        Some(ref paths) if !paths.is_empty() => {
            let mut file_ids = Vec::with_capacity(paths.len());
            for path in paths {
                match upload_file(&client, api_key, path).await {
                    Ok(id) => file_ids.push(id),
                    Err(e) => {
                        return Err(format!("Upload failed for {}: {}", path, e));
                    }
                }
            }
            let mut content_parts: Vec<JsonValue> = file_ids
                .into_iter()
                .map(|file_id| {
                    serde_json::json!({
                        "type": "file",
                        "file": { "file_id": file_id }
                    })
                })
                .collect();
            let text = message.trim();
            if !text.is_empty() {
                content_parts.push(serde_json::json!({ "type": "text", "text": text }));
            } else {
                content_parts.push(serde_json::json!({
                    "type": "text",
                    "text": "Please summarize or answer based on the attached documents."
                }));
            }
            let content = JsonValue::Array(content_parts);
            (content, "gpt-4o".to_string())
        }
        _ => (JsonValue::String(message.clone()), "gpt-4o-mini".to_string()),
    };

    let body = ChatRequest {
        model,
        messages: vec![ChatMessageRequest {
            role: "user".to_string(),
            content: user_content,
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
