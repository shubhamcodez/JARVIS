//! Single-step executor: interpret subgoal, run one action via harness, verify, trace, recovery.

use crate::agent::actions::{AgentAction, RiskLevel};
use crate::agent::harness_browser::{BrowserHarness, Snapshot};
use crate::agent::recovery;
use crate::agent::session;
use crate::agent::trace;
use crate::agent::verifier;

/// Extract URL from subgoal text (e.g. "Open https://example.com" or "Navigate to example.com").
fn url_from_subgoal(subgoal: &str) -> String {
    let s = subgoal.trim();
    if let Some(i) = s.find("https://") {
        let rest = &s[i..];
        let end = rest
            .find(|c: char| c.is_whitespace() || c == '"' || c == ')')
            .unwrap_or(rest.len());
        return rest[..end].to_string();
    }
    if let Some(i) = s.find("http://") {
        let rest = &s[i..];
        let end = rest
            .find(|c: char| c.is_whitespace() || c == '"' || c == ')')
            .unwrap_or(rest.len());
        return rest[..end].to_string();
    }
    if let Some(lower) = s.to_lowercase().strip_prefix("open ") {
        let domain = lower
            .trim()
            .split_whitespace()
            .next()
            .unwrap_or("example.com");
        return format!("https://{}", domain.trim_start_matches("https://").trim_start_matches("http://"));
    }
    if let Some(lower) = s.to_lowercase().strip_prefix("navigate to ") {
        let domain = lower.trim().split_whitespace().next().unwrap_or("example.com");
        return format!("https://{}", domain.trim_start_matches("https://").trim_start_matches("http://"));
    }
    "https://example.com".to_string()
}

/// Run one step for the current subgoal. Returns updated session summary or error.
/// If the chosen action is high-risk, sets session to Blocked and returns (call agent_approve_action to continue).
pub fn run_one_step(session_id: &str) -> Result<crate::agent::AgentSessionSummary, String> {
    let mut sess = session::load_session(session_id)?
        .ok_or_else(|| "Session not found".to_string())?;

    if sess.current_subgoal_index >= sess.subgoals.len() {
        sess.status = session::SessionStatus::Completed;
        session::save_session(&sess)?;
        trace::append(session_id, &trace::TraceEvent::SessionEnd { status: "completed".to_string() })?;
        let trace_lines = trace::read_trace(session_id)?;
        return Ok(crate::agent::summary_from_session(&sess, &trace_lines));
    }

    let subgoal = sess.subgoals[sess.current_subgoal_index].clone();
    let action = AgentAction::OpenUrl {
        url: url_from_subgoal(&subgoal),
    };

    trace::append(
        session_id,
        &trace::TraceEvent::ActionChosen {
            action: action.clone(),
        },
    )?;

    if matches!(action.risk_level(), RiskLevel::High | RiskLevel::Medium) {
        sess.status = session::SessionStatus::Blocked;
        sess.blocked_reason = Some("awaiting_approval".to_string());
        sess.pending_action = Some(action.clone());
        session::save_session(&sess)?;
        trace::append(
            session_id,
            &trace::TraceEvent::HumanApprovalRequested {
                reason: format!("{:?}", action.risk_level()),
            },
        )?;
        let trace_lines = trace::read_trace(session_id)?;
        return Ok(crate::agent::summary_from_session(&sess, &trace_lines));
    }

    execute_action_and_apply_result(session_id, &mut sess, &action)
}

fn execute_action_and_apply_result(
    session_id: &str,
    sess: &mut session::AgentSession,
    action: &AgentAction,
) -> Result<crate::agent::AgentSessionSummary, String> {
    let url = action
        .open_url()
        .ok_or_else(|| "Only OpenUrl supported in this step".to_string())?;
    let mut harness = BrowserHarness::new();
    let run_result = harness.open_url(url);
    let success = run_result.is_ok();

    trace::append(
        session_id,
        &trace::TraceEvent::ActionExecuted {
            action: action.clone(),
            success,
        },
    )?;

    let snapshot_opt = if success {
        harness.get_snapshot(false).ok()
    } else {
        None
    };
    apply_verification_and_recovery(session_id, sess, action, success, run_result, snapshot_opt)
}

fn apply_verification_and_recovery(
    session_id: &str,
    sess: &mut session::AgentSession,
    action: &AgentAction,
    success: bool,
    run_result: Result<(), String>,
    snapshot_opt: Option<Snapshot>,
) -> Result<crate::agent::AgentSessionSummary, String> {
    let (passed, detail) = if success {
        if let Some(ref snapshot) = snapshot_opt {
            verifier::verify_after_open(snapshot, None, None)
        } else {
            (true, None)
        }
    } else {
        (false, Some(run_result.err().unwrap_or_else(|| "unknown".to_string())))
    };

    trace::append(
        session_id,
        &trace::TraceEvent::VerifierResult {
            passed,
            detail: detail.clone(),
        },
    )?;

    if passed {
        sess.current_subgoal_index += 1;
        sess.last_checkpoint_index = sess.current_subgoal_index;
        sess.retries = 0;
        if sess.current_subgoal_index >= sess.subgoals.len() {
            sess.status = session::SessionStatus::Completed;
            trace::append(session_id, &trace::TraceEvent::SessionEnd { status: "completed".to_string() })?;
        }
    } else {
        sess.retries += 1;
        let recovery_action = recovery::decide(&sess, detail.as_deref());
        match recovery_action {
            recovery::RecoveryAction::Abort => {
                sess.status = session::SessionStatus::Failed;
                trace::append(
                    session_id,
                    &trace::TraceEvent::Retry {
                        subgoal_index: sess.current_subgoal_index,
                        reason: format!("abort after {} retries", sess.retries),
                    },
                )?;
                trace::append(session_id, &trace::TraceEvent::SessionEnd { status: "failed".to_string() })?;
            }
            recovery::RecoveryAction::Retry => {
                trace::append(
                    session_id,
                    &trace::TraceEvent::Retry {
                        subgoal_index: sess.current_subgoal_index,
                        reason: detail.unwrap_or_else(|| "verification failed".to_string()),
                    },
                )?;
            }
            _ => {}
        }
    }

    session::save_session(sess)?;
    let trace_lines = trace::read_trace(session_id)?;
    Ok(crate::agent::summary_from_session(sess, &trace_lines))
}

/// Execute the pending action after human approval. Clears pending and unblocks.
pub fn run_approved_action(session_id: &str, approved: bool) -> Result<crate::agent::AgentSessionSummary, String> {
    let mut sess = session::load_session(session_id)?
        .ok_or_else(|| "Session not found".to_string())?;

    trace::append(
        session_id,
        &trace::TraceEvent::HumanApprovalResult { approved },
    )?;

    let action = match sess.pending_action.take() {
        Some(a) => a,
        None => {
            sess.blocked_reason = None;
            sess.status = session::SessionStatus::Running;
            session::save_session(&sess)?;
            let trace_lines = trace::read_trace(session_id)?;
            return Ok(crate::agent::summary_from_session(&sess, &trace_lines));
        }
    };

    if !approved {
        sess.status = session::SessionStatus::Stopped;
        sess.blocked_reason = None;
        session::save_session(&sess)?;
        trace::append(session_id, &trace::TraceEvent::SessionEnd { status: "stopped".to_string() })?;
        let trace_lines = trace::read_trace(session_id)?;
        return Ok(crate::agent::summary_from_session(&sess, &trace_lines));
    }

    sess.status = session::SessionStatus::Running;
    sess.blocked_reason = None;
    session::save_session(&sess)?;

    let url = action.open_url().ok_or_else(|| "Only OpenUrl supported".to_string())?;
    let mut harness = BrowserHarness::new();
    let run_result = harness.open_url(url);
    let success = run_result.is_ok();

    trace::append(
        session_id,
        &trace::TraceEvent::ActionExecuted {
            action: action.clone(),
            success,
        },
    )?;

    let snapshot_opt = if success {
        harness.get_snapshot(false).ok()
    } else {
        None
    };
    apply_verification_and_recovery(
        session_id,
        &mut sess,
        &action,
        success,
        run_result,
        snapshot_opt,
    )
}
