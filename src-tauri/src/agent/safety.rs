//! Safety kernel: risk classification, approval gates, and execution constraints.
//!
//! - **Isolation**: Browser harness (headless_chrome) runs in a separate Chrome process
//!   with its own profile; no shared cookies or session with the user's main browser.
//! - **Approval gates**: High- and medium-risk actions (see actions::AgentAction::risk_level)
//!   require human approval via the UI before execution; the session is set to Blocked
//!   until the user approves or rejects.
//! - **Least-privilege**: Credentials (e.g. OPENAI_API_KEY) are loaded from env and not
//!   stored in agent state; future vault integration can restrict which actions get access.
//! - **Recovery cap**: max_retries per session limits automatic retries before abort.

/// Actions with this risk level or higher require human approval before execution.
pub const APPROVAL_REQUIRED_RISK_LEVEL: &str = "medium";
