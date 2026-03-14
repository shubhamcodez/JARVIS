//! Structured action schema for the computer-use agent.
//! No arbitrary free-form behavior; all actions use this enum.

use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
#[serde(tag = "type", rename_all = "snake_case")]
pub enum AgentAction {
    Click { selector: String },
    Type { selector: String, text: String },
    Scroll { container: String, amount: i32 },
    WaitFor { condition: String },
    OpenUrl { url: String },
    GoBack,
    RequestHumanApproval { reason: String },
    StopWithStatus { status: String },
}

impl AgentAction {
    /// URL for OpenUrl action, if any.
    pub fn open_url(&self) -> Option<&str> {
        match self {
            AgentAction::OpenUrl { url } => Some(url.as_str()),
            _ => None,
        }
    }

    /// Classify risk for approval gating. High-risk actions require human approval.
    pub fn risk_level(&self) -> RiskLevel {
        match self {
            AgentAction::RequestHumanApproval { .. } | AgentAction::StopWithStatus { .. } => {
                RiskLevel::None
            }
            AgentAction::Type { text, .. } => {
                if text.contains("password") || text.contains("payment") || text.len() > 200 {
                    RiskLevel::High
                } else {
                    RiskLevel::Low
                }
            }
            AgentAction::OpenUrl { url } => {
                if url.contains("bank") || url.contains("pay") || url.contains("login") {
                    RiskLevel::Medium
                } else {
                    RiskLevel::Low
                }
            }
            AgentAction::Click { .. }
            | AgentAction::Scroll { .. }
            | AgentAction::WaitFor { .. }
            | AgentAction::GoBack => RiskLevel::Low,
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum RiskLevel {
    None,
    Low,
    Medium,
    High,
}
