//! Load .env for OPENAI_API_KEY and similar.

/// Load .env from current dir, parent, or next to the executable.
pub fn load_env() {
    let _ = dotenvy::dotenv();
    if std::env::var("OPENAI_API_KEY").is_err() {
        let _ = dotenvy::from_path("../.env");
    }
    if std::env::var("OPENAI_API_KEY").is_err() {
        if let Ok(exe) = std::env::current_exe() {
            if let Some(dir) = exe.parent() {
                let _ = dotenvy::from_path(dir.join(".env"));
            }
        }
    }
}
