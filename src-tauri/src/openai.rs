//! OpenAI API client: file upload, Responses API (documents), and Chat Completions (text-only).

use std::fs;
use reqwest::Client;
use serde::{Deserialize, Serialize};
use serde_json::Value as JsonValue;

#[derive(Debug, Deserialize)]
struct OpenAIFileResponse {
    id: String,
}

// --- Responses API (for document upload) ---
#[derive(Debug, Serialize)]
struct ResponsesRequest {
    model: String,
    input: Vec<ResponsesInputItem>,
}

#[derive(Debug, Serialize)]
struct ResponsesInputItem {
    role: String,
    content: Vec<JsonValue>,
}

// --- Chat Completions API (text-only, no files) ---
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

/// Extract assistant text from Responses API output array.
/// Handles output as array of messages with content[].type == "output_text".
fn extract_output_text(output: &[JsonValue]) -> String {
    let mut parts = Vec::new();
    for item in output {
        let obj = match item.as_object() {
            Some(o) => o,
            None => continue,
        };
        let content = match obj.get("content").and_then(|c| c.as_array()) {
            Some(c) => c,
            None => continue,
        };
        for part in content {
            let part_obj = match part.as_object() {
                Some(o) => o,
                None => continue,
            };
            if part_obj.get("type").and_then(|t| t.as_str()) != Some("output_text") {
                continue;
            }
            if let Some(text) = part_obj.get("text").and_then(|t| t.as_str()) {
                parts.push(text);
            }
        }
    }
    let reply = parts.join("").trim().to_string();
    if reply.is_empty() {
        "No text in response.".to_string()
    } else {
        reply
    }
}

/// Send a chat request. With attachments: uses Responses API (document upload).
/// Without: uses Chat Completions API.
pub async fn chat(
    api_key: &str,
    message: String,
    attachment_paths: Option<Vec<String>>,
) -> Result<String, String> {
    let client = Client::new();

    if let Some(ref paths) = attachment_paths {
        if !paths.is_empty() {
            return responses_with_files(&client, api_key, &message, paths).await;
        }
    }

    chat_completion_only(&client, api_key, message).await
}

/// Use Responses API with uploaded files (supports PDF, docx, etc.).
async fn responses_with_files(
    client: &Client,
    api_key: &str,
    message: &str,
    paths: &[String],
) -> Result<String, String> {
    let mut file_ids = Vec::with_capacity(paths.len());
    for path in paths {
        let id = upload_file(client, api_key, path)
            .await
            .map_err(|e| format!("Upload failed for {}: {}", path, e))?;
        file_ids.push(id);
    }

    let mut content: Vec<JsonValue> = file_ids
        .into_iter()
        .map(|file_id| serde_json::json!({ "type": "input_file", "file_id": file_id }))
        .collect();
    let text = message.trim();
    if !text.is_empty() {
        content.push(serde_json::json!({ "type": "input_text", "text": text }));
    } else {
        content.push(serde_json::json!({
            "type": "input_text",
            "text": "Please summarize or answer based on the attached documents."
        }));
    }

    let body = ResponsesRequest {
        model: "gpt-4o".to_string(),
        input: vec![ResponsesInputItem {
            role: "user".to_string(),
            content,
        }],
    };

    let res = client
        .post("https://api.openai.com/v1/responses")
        .bearer_auth(api_key)
        .json(&body)
        .send()
        .await
        .map_err(|e| e.to_string())?;

    let status = res.status();
    let raw = res.text().await.unwrap_or_default();
    if !status.is_success() {
        return Err(format!("API error {}: {}", status, raw));
    }

    let json: JsonValue = serde_json::from_str(&raw).map_err(|e| e.to_string())?;
    let empty: &[JsonValue] = &[];
    let output = json
        .get("output")
        .and_then(|o| o.as_array())
        .map_or(empty, |a| a.as_slice());
    Ok(extract_output_text(output))
}

/// Text-only chat via Chat Completions API.
async fn chat_completion_only(
    client: &Client,
    api_key: &str,
    message: String,
) -> Result<String, String> {
    let body = ChatRequest {
        model: "gpt-4o-mini".to_string(),
        messages: vec![ChatMessageRequest {
            role: "user".to_string(),
            content: JsonValue::String(message),
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
