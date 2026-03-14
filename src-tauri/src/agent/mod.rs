//! Computer-use agent: session manager, planner, actions, trace, harness, verifier, recovery, executor.

pub mod actions;
pub mod executor;
pub mod harness_browser;
pub mod harness_desktop;
pub mod planner;
pub mod recovery;
pub mod safety;
pub mod session;
pub mod trace;
pub mod verifier;

use serde::Serialize;

#[derive(Serialize)]
pub struct AgentSessionSummary {
    pub id: String,
    pub goal: String,
    pub status: String,
    pub subgoals: Vec<String>,
    pub current_subgoal_index: usize,
    pub trace_lines: Vec<String>,
    /// Set when status is "blocked" (e.g. "awaiting_approval").
    pub blocked_reason: Option<String>,
    /// Pending action description for approval modal.
    pub pending_action_description: Option<String>,
}

#[tauri::command]
pub async fn agent_submit_goal(goal: String) -> Result<AgentSessionSummary, String> {
    let goal = goal.trim();
    if goal.is_empty() {
        return Err("Goal cannot be empty.".to_string());
    }
    let id = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map_err(|e| e.to_string())?
        .as_secs()
        .to_string();
    let session = session::AgentSession::new(id.clone(), goal.to_string());
    session::save_session(&session)?;
    trace::append(
        &id,
        &trace::TraceEvent::SessionCreated {
            goal: goal.to_string(),
        },
    )?;
    let _ = planner::plan_subgoals(&id, goal).await?;
    let session = session::load_session(&id)?
        .ok_or_else(|| "Session not found after plan".to_string())?;
    let trace_lines = trace::read_trace(&id)?;
    Ok(summary_from_session(&session, &trace_lines))
}

fn status_string(s: &session::SessionStatus) -> String {
    match s {
        session::SessionStatus::Planned => "planned",
        session::SessionStatus::Running => "running",
        session::SessionStatus::Blocked => "blocked",
        session::SessionStatus::Completed => "completed",
        session::SessionStatus::Failed => "failed",
        session::SessionStatus::Stopped => "stopped",
    }
    .to_string()
}

pub(crate) fn summary_from_session(session: &session::AgentSession, trace_lines: &[String]) -> AgentSessionSummary {
    AgentSessionSummary {
        id: session.id.clone(),
        goal: session.goal.clone(),
        status: status_string(&session.status),
        subgoals: session.subgoals.clone(),
        current_subgoal_index: session.current_subgoal_index,
        trace_lines: trace_lines.to_vec(),
        blocked_reason: session.blocked_reason.clone(),
        pending_action_description: session.pending_action.as_ref().map(|a| format!("{:?}", a)),
    }
}

#[tauri::command]
pub fn agent_list_sessions() -> Result<Vec<String>, String> {
    session::list_session_ids()
}

#[tauri::command]
pub fn agent_run_step(session_id: String) -> Result<AgentSessionSummary, String> {
    executor::run_one_step(&session_id)
}

#[tauri::command]
pub fn agent_approve_action(session_id: String, approved: bool) -> Result<AgentSessionSummary, String> {
    executor::run_approved_action(&session_id, approved)
}

/// Return outcome for eval/replay: completed, failed, stopped, or blocked.
#[tauri::command]
pub fn agent_get_session_outcome(id: String) -> Result<String, String> {
    let session = session::load_session(&id)?
        .ok_or_else(|| "Session not found.".to_string())?;
    Ok(match session.status {
        session::SessionStatus::Completed => "completed",
        session::SessionStatus::Failed => "failed",
        session::SessionStatus::Stopped => "stopped",
        session::SessionStatus::Blocked => "blocked",
        session::SessionStatus::Planned | session::SessionStatus::Running => "running",
    }
    .to_string())
}

#[tauri::command]
pub fn agent_get_session(id: String) -> Result<AgentSessionSummary, String> {
    let session = session::load_session(&id)?
        .ok_or_else(|| "Session not found.".to_string())?;
    let trace_lines = trace::read_trace(&id)?;
    Ok(summary_from_session(&session, &trace_lines))
}
