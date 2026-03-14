//! File and folder picker commands.

#[tauri::command]
pub async fn open_file_picker(app: tauri::AppHandle) -> Result<Vec<String>, String> {
    use tauri_plugin_dialog::DialogExt;
    let paths = tauri::async_runtime::spawn_blocking(move || {
        app.dialog().file().blocking_pick_files()
    })
    .await
    .map_err(|e| e.to_string())?
    .unwrap_or_default();
    let strings: Vec<String> = paths.into_iter().map(|p| p.to_string()).collect();
    Ok(strings)
}

#[tauri::command]
pub async fn open_folder_picker(app: tauri::AppHandle) -> Result<Option<String>, String> {
    use tauri_plugin_dialog::DialogExt;
    let path = tauri::async_runtime::spawn_blocking(move || {
        app.dialog().file().blocking_pick_folder()
    })
    .await
    .map_err(|e| e.to_string())?;
    Ok(path.map(|p| p.to_string()))
}
