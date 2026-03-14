//! Recovery policy: retry, abort after N failures, escalate.

use crate::agent::session;

/// Recovery decision after a failed step.
#[derive(Debug, Clone)]
pub enum RecoveryAction {
    Retry,
    Abort,
    EscalateToHuman(String),
}

/// Decide recovery from session state (retries, max_retries).
pub fn decide(session: &session::AgentSession, _verifier_detail: Option<&str>) -> RecoveryAction {
    if session.retries >= session.max_retries {
        RecoveryAction::Abort
    } else {
        RecoveryAction::Retry
    }
}
