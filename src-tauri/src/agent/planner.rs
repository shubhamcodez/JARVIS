//! Planner: break user goal into subgoals via OpenAI. Output stored in session.

use crate::agent::{session, trace};
use crate::env;
use crate::openai;

const PLANNER_SYSTEM: &str = r#"You are a task planner for a computer-use agent. Given a user goal, output a JSON array of subgoal strings. Each subgoal should be one clear step (e.g. "Open the login page", "Enter username and password", "Navigate to Statements", "Download the PDF"). Output only the JSON array, no other text. Example: ["Open https://example.com", "Click the Login link", "Type username into the email field"]"#;

/// Plan subgoals for the given goal; updates session and trace.
pub async fn plan_subgoals(session_id: &str, goal: &str) -> Result<Vec<String>, String> {
    env::load_env();
    let api_key = std::env::var("OPENAI_API_KEY")
        .map_err(|_| "OPENAI_API_KEY not set.".to_string())?;

    let reply = openai::chat_with_system(api_key.as_str(), PLANNER_SYSTEM, goal).await?;
    let subgoals = parse_subgoals_from_reply(&reply)?;

    let mut sess = session::load_session(session_id)?
        .ok_or_else(|| "Session not found".to_string())?;
    sess.subgoals = subgoals.clone();
    sess.status = crate::agent::session::SessionStatus::Planned;
    session::save_session(&sess)?;

    trace::append(
        session_id,
        &trace::TraceEvent::PlanReady {
            subgoals: subgoals.clone(),
        },
    )?;

    Ok(subgoals)
}

fn parse_subgoals_from_reply(reply: &str) -> Result<Vec<String>, String> {
    let trimmed = reply.trim();
    // Strip markdown code block if present
    let json_str = trimmed
        .strip_prefix("```json")
        .or_else(|| trimmed.strip_prefix("```"))
        .and_then(|s| s.strip_suffix("```").map(|t| t.trim()))
        .unwrap_or(trimmed);
    let arr: Vec<String> = serde_json::from_str(json_str).map_err(|e| e.to_string())?;
    Ok(arr)
}
