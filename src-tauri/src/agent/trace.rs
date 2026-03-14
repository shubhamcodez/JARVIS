//! Append-only trace log per session: observations, actions, verifier result, retries, outcome.

use std::fs::OpenOptions;
use std::io::Write;
use std::path::PathBuf;

use serde::Serialize;

use super::actions::AgentAction;
use super::session;

#[derive(Debug, Clone, Serialize)]
#[serde(tag = "event", rename_all = "snake_case")]
pub enum TraceEvent {
    SessionCreated { goal: String },
    PlanReady { subgoals: Vec<String> },
    ActionChosen { action: AgentAction },
    ActionExecuted { action: AgentAction, success: bool },
    VerifierResult { passed: bool, detail: Option<String> },
    Retry { subgoal_index: usize, reason: String },
    Checkpoint { subgoal_index: usize },
    Recovery { strategy: String, detail: Option<String> },
    HumanApprovalRequested { reason: String },
    HumanApprovalResult { approved: bool },
    SessionEnd { status: String },
}

fn trace_file_path(session_id: &str) -> Result<PathBuf, String> {
    let dir = session::traces_dir()?;
    let safe_id = session_id.replace(|c: char| !c.is_ascii_alphanumeric(), "_");
    Ok(dir.join(format!("{}.jsonl", safe_id)))
}

pub fn append(session_id: &str, event: &TraceEvent) -> Result<(), String> {
    let path = trace_file_path(session_id)?;
    let mut f = OpenOptions::new()
        .create(true)
        .append(true)
        .open(&path)
        .map_err(|e| e.to_string())?;
    let line = serde_json::to_string(event).map_err(|e| e.to_string())?;
    writeln!(f, "{}", line).map_err(|e| e.to_string())?;
    Ok(())
}

pub fn read_trace(session_id: &str) -> Result<Vec<String>, String> {
    let path = trace_file_path(session_id)?;
    if !path.exists() {
        return Ok(Vec::new());
    }
    let content = std::fs::read_to_string(&path).map_err(|e| e.to_string())?;
    let lines: Vec<String> = content
        .lines()
        .map(|s| s.trim().to_string())
        .filter(|s| !s.is_empty())
        .collect();
    Ok(lines)
}
