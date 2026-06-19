mod commands;

use commands::*;

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .invoke_handler(tauri::generate_handler![
            list_stocks,
            add_stock,
            delete_stock,
            import_stocks,
            sync_all_stocks,
            sync_stock,
            get_kline,
            get_formulas,
            get_u1_buy_points,
            start_exploration,
            pause_exploration,
            stop_exploration,
            get_settings,
            set_setting,
            get_all_settings,
            test_api_connection,
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}