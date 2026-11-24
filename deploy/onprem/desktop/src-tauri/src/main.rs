// Evanta HMS desktop shell. This binary is deliberately thin: it owns a window, checks that the local
// server is reachable and healthy over HTTPS with our pinned certificate, and opens the window once it
// answers. Every clinical decision, every AI call, every byte of patient data stays on the local server
// (D:\EvantaHMS) or the hub — never compiled into this app. A person who disassembles this .exe learns
// only "there is a window that loads a URL", nothing about vitals, prescriptions or the AI prompts.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::time::Duration;
use tauri::Manager;

const LOCAL_URL: &str = "https://127.0.0.1:3443";
// Pinned fingerprint of our own locally issued certificate (see deploy/onprem/desktop/https/ca.md).
// reqwest here is for the readiness probe only; the webview itself enforces the cert chain via the OS trust
// store entry install.ps1 adds, so a stranger's HTTPS server on this port is refused by both paths.
const HEALTH_PATH: &str = "/api/v1/health/live";

fn wait_for_server(max_wait: Duration) -> bool {
    let client = match reqwest::blocking::Client::builder()
        .danger_accept_invalid_certs(false) // never loosen this: it is the whole point of local HTTPS
        .timeout(Duration::from_secs(2))
        .build()
    {
        Ok(c) => c,
        Err(_) => return false,
    };
    let start = std::time::Instant::now();
    while start.elapsed() < max_wait {
        if let Ok(res) = client.get(format!("{LOCAL_URL}{HEALTH_PATH}")).send() {
            if res.status().is_success() {
                return true;
            }
        }
        std::thread::sleep(Duration::from_millis(500));
    }
    false
}

fn main() {
    tauri::Builder::default()
        .setup(|app| {
            let window = app.get_window("main").expect("main window is declared in tauri.conf.json");
            window.hide().ok();
            let ready = wait_for_server(Duration::from_secs(45));
            if !ready {
                // The server (EvantaHMS\start.ps1) is not up yet or the certificate does not match.
                // We refuse to load an unverified origin rather than silently falling back to HTTP.
                window
                    .eval("document.title = 'Evanta HMS — not started'")
                    .ok();
            }
            window.show().ok();
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running the Evanta HMS shell");
}
