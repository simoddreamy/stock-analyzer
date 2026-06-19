#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod commands;

use tauri::Manager;

fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .setup(|app| {
            let window = app.get_webview_window("main").unwrap();
            window.set_title("Stock Analyzer").unwrap();
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            commands::list_stocks,
            commands::add_stock,
            commands::delete_stock,
            commands::import_stocks,
            commands::sync_all_stocks,
            commands::sync_stock,
            commands::get_kline,
            commands::get_indicators,
            commands::get_formulas,
            commands::get_u1_buy_points,
            commands::start_exploration,
            commands::pause_exploration,
            commands::stop_exploration,
            commands::get_settings,
            commands::set_setting,
            commands::get_all_settings,
            commands::test_api_connection,
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}