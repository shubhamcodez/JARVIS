//! Desktop harness: list windows, focus, screenshot, send keys.
//! MVP: stub implementation; extend with win-screenshot or windows crate for production.

use serde::Serialize;

/// A desktop window (id and title).
#[derive(Debug, Clone, Serialize)]
pub struct DesktopWindow {
    pub id: String,
    pub title: String,
}

/// List visible windows. Stub: returns empty on all platforms until implemented.
pub fn list_windows() -> Result<Vec<DesktopWindow>, String> {
    #[cfg(target_os = "windows")]
    {
        list_windows_windows()
    }
    #[cfg(not(target_os = "windows"))]
    {
        let _ = ();
        Ok(Vec::new())
    }
}

#[cfg(target_os = "windows")]
fn list_windows_windows() -> Result<Vec<DesktopWindow>, String> {
    // TODO: use windows crate EnumWindows + GetWindowText to enumerate.
    Ok(Vec::new())
}

/// Focus a window by id. Stub: no-op until implemented.
pub fn focus_window(_id: &str) -> Result<(), String> {
    Ok(())
}

/// Capture full screen to PNG bytes (base64). Stub: returns error until implemented.
pub fn capture_screen() -> Result<String, String> {
    Err("Desktop screenshot not implemented yet. Use browser harness for now.".to_string())
}
