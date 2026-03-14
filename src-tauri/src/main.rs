// Prevents additional console window on Windows in release
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod agent;
mod chat_log;
mod dialog;
mod env;
mod openai;
mod storage;
mod window;

#[tauri::command]
async fn chatbot_response(
    message: String,
    attachment_paths: Option<Vec<String>>,
) -> Result<String, String> {
    env::load_env();
    let api_key = std::env::var("OPENAI_API_KEY")
        .map_err(|_| "OPENAI_API_KEY not set. Add it to a .env file in the project root.")?;
    openai::chat(&api_key, message, attachment_paths).await
}

fn main() {
    env::load_env();

    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_shell::init())
        .manage(chat_log::ChatLogState::default())
        .invoke_handler(tauri::generate_handler![
            chatbot_response,
            window::window_minimize,
            window::window_close,
            window::window_toggle_maximize,
            chat_log::append_chat_log,
            chat_log::list_chats,
            dialog::open_file_picker,
            dialog::open_folder_picker,
            storage::get_chats_storage_path,
            storage::set_chats_storage_path,
            agent::agent_submit_goal,
            agent::agent_list_sessions,
            agent::agent_get_session,
            agent::agent_run_step,
            agent::agent_approve_action,
            agent::agent_get_session_outcome,
        ])
        .plugin(tauri_plugin_dialog::init())
        .run(tauri::generate_context!())
        .expect("error while running Tauri application");
}
