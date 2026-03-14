//! Per-step verification: did the action succeed? Page change, URL, selector, etc.

use crate::agent::harness_browser::Snapshot;

/// Simple verifier: check URL and optional expected substring in body.
pub fn verify_after_open(
    snapshot: &Snapshot,
    expected_url_contains: Option<&str>,
    expected_body_contains: Option<&str>,
) -> (bool, Option<String>) {
    if let Some(needle) = expected_url_contains {
        if !snapshot.url.contains(needle) {
            return (
                false,
                Some(format!("URL {:?} does not contain {:?}", snapshot.url, needle)),
            );
        }
    }
    if let Some(needle) = expected_body_contains {
        if !snapshot.body_text.contains(needle) {
            return (
                false,
                Some(format!(
                    "Body text does not contain {:?}",
                    needle.chars().take(50).collect::<String>()
                )),
            );
        }
    }
    (true, None)
}
