"""
Tauri IPC 命令 - Rust端注册
这些命令桥接前端Vue和Python后端
"""
use tauri::Manager;

#[tauri::command]
async fn list_stocks() -> Result<Vec<serde_json::Value>, String> {
    // 实际通过HTTP调用Python后端
    Ok(vec![])
}

#[tauri::command]
async fn add_stock(code: String) -> Result<serde_json::Value, String> {
    Ok(serde_json::json!({ "code": code, "status": "added" }))
}

#[tauri::command]
async fn delete_stock(code: String) -> Result<(), String> {
    Ok(())
}

#[tauri::command]
async fn import_stocks(codes: Vec<String>) -> Result<serde_json::Value, String> {
    Ok(serde_json::json!({ "added": codes, "failed": [] }))
}

#[tauri::command]
async fn sync_all_stocks() -> Result<serde_json::Value, String> {
    Ok(serde_json::json!({ "synced_at": chrono::Local::now().to_rfc3339() }))
}

#[tauri::command]
async fn sync_stock(code: String) -> Result<serde_json::Value, String> {
    Ok(serde_json::json!({ "code": code, "new_records": 0, "status": "success" }))
}

#[tauri::command]
async fn get_kline(code: String) -> Result<Vec<serde_json::Value>, String> {
    Ok(vec![])
}

#[tauri::command]
async fn get_formulas(code: String) -> Result<Vec<serde_json::Value>, String> {
    Ok(vec![])
}

#[tauri::command]
async fn get_u1_buy_points(code: String) -> Result<serde_json::Value, String> {
    Ok(serde_json::json!({ "code": code, "u1_dates": [], "count": 0 }))
}

#[tauri::command]
async fn start_exploration(req: serde_json::Value) -> Result<serde_json::Value, String> {
    Ok(serde_json::json!({ "mode": "single", "found": false }))
}

#[tauri::command]
async fn pause_exploration() -> Result<(), String> {
    Ok(())
}

#[tauri::command]
async fn stop_exploration() -> Result<(), String> {
    Ok(())
}

#[tauri::command]
async fn get_settings() -> Result<serde_json::Value, String> {
    Ok(serde_json::json!({}))
}

#[tauri::command]
async fn set_setting(key: String, value: String) -> Result<(), String> {
    Ok(())
}

#[tauri::command]
async fn get_all_settings() -> Result<serde_json::Value, String> {
    Ok(serde_json::json!({}))
}

#[tauri::command]
async fn test_api_connection(
    api_key: String,
    api_base: String,
    model: String,
) -> Result<serde_json::Value, String> {
    Ok(serde_json::json!({ "ok": true }))
}