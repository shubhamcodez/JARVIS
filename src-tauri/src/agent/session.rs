//! Durable task state: goal, subgoals, status, checkpoints, retries, completion criteria.
//! Persisted to disk so sessions survive restarts.

use std::fs;
use std::path::PathBuf;

use serde::{Deserialize, Serialize};

use crate::agent::actions::AgentAction;
use crate::storage;

/// Session status.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
#[serde(rename_all = "snake_case")]
pub enum SessionStatus {
    Planned,    // subgoals set, not yet running
    Running,    // orchestrator active
    Blocked,    // waiting for human or resource
    Completed,  // success
    Failed,     // abort after retries
    Stopped,    // user stopped
}

/// Durable session state.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AgentSession {
    pub id: String,
    pub goal: String,
    pub status: SessionStatus,
    pub subgoals: Vec<String>,
    /// Index of current (or next) subgoal.
    pub current_subgoal_index: usize,
    /// Last successful checkpoint: subgoal index we can revert to.
    pub last_checkpoint_index: usize,
    pub retries: u32,
    pub max_retries: u32,
    /// Why blocked (e.g. "awaiting_approval", "credentials_needed").
    pub blocked_reason: Option<String>,
    /// Action waiting for human approval; when set, status is Blocked.
    #[serde(default)]
    pub pending_action: Option<AgentAction>,
    pub created_at_secs: u64,
    pub updated_at_secs: u64,
}

impl AgentSession {
    pub fn new(id: String, goal: String) -> Self {
        let now = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap()
            .as_secs();
        AgentSession {
            id: id.clone(),
            goal,
            status: SessionStatus::Planned,
            subgoals: Vec::new(),
            current_subgoal_index: 0,
            last_checkpoint_index: 0,
            retries: 0,
            max_retries: 3,
            blocked_reason: None,
            pending_action: None,
            created_at_secs: now,
            updated_at_secs: now,
        }
    }

    pub fn current_subgoal(&self) -> Option<&str> {
        self.subgoals.get(self.current_subgoal_index).map(|s| s.as_str())
    }

    pub fn is_done(&self) -> bool {
        matches!(
            self.status,
            SessionStatus::Completed | SessionStatus::Failed | SessionStatus::Stopped
        )
    }
}

/// Base directory for agent data (sessions + traces). Sibling to chats dir.
fn agent_data_dir() -> Result<PathBuf, String> {
    let chats = storage::chats_dir()?;
    let parent = chats.parent().unwrap_or(&chats);
    let dir = parent.join("agent_data");
    std::fs::create_dir_all(&dir).map_err(|e| e.to_string())?;
    Ok(dir)
}

fn sessions_dir() -> Result<PathBuf, String> {
    let dir = agent_data_dir()?.join("sessions");
    std::fs::create_dir_all(&dir).map_err(|e| e.to_string())?;
    Ok(dir)
}

fn session_path(id: &str) -> Result<PathBuf, String> {
    let safe_id = id.replace(|c: char| !c.is_ascii_alphanumeric(), "_");
    Ok(sessions_dir()?.join(format!("{}.json", safe_id)))
}

pub fn save_session(session: &AgentSession) -> Result<(), String> {
    let path = session_path(&session.id)?;
    let updated = AgentSession {
        updated_at_secs: std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap()
            .as_secs(),
        ..session.clone()
    };
    let json = serde_json::to_string_pretty(&updated).map_err(|e| e.to_string())?;
    fs::write(path, json).map_err(|e| e.to_string())?;
    Ok(())
}

pub fn load_session(id: &str) -> Result<Option<AgentSession>, String> {
    let path = session_path(id)?;
    if !path.exists() {
        return Ok(None);
    }
    let json = fs::read_to_string(&path).map_err(|e| e.to_string())?;
    let session: AgentSession = serde_json::from_str(&json).map_err(|e| e.to_string())?;
    Ok(Some(session))
}

pub fn list_session_ids() -> Result<Vec<String>, String> {
    let dir = sessions_dir()?;
    let mut ids = Vec::new();
    for entry in fs::read_dir(&dir).map_err(|e| e.to_string())? {
        let entry = entry.map_err(|e| e.to_string())?;
        let path = entry.path();
        if path.extension().and_then(|e| e.to_str()) == Some("json") {
            if let Some(stem) = path.file_stem() {
                ids.push(stem.to_string_lossy().replace('_', "-"));
            }
        }
    }
    ids.sort_by(|a, b| b.cmp(a));
    Ok(ids)
}

pub fn traces_dir() -> Result<PathBuf, String> {
    let dir = agent_data_dir()?.join("traces");
    std::fs::create_dir_all(&dir).map_err(|e| e.to_string())?;
    Ok(dir)
}
