//! The desktop shell. It starts the bundled Python backend (the "sidecar"), waits for it to
//! say which port it got, and points the window at it. The backend serves the web UI and the
//! API from that one origin, which also gives the YouTube player the real http:// origin it
//! needs. In `tauri dev` no sidecar is started: the window loads the Vite dev server and
//! `make dev` runs the backend.

use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex};
use std::time::Duration;

use tauri::path::BaseDirectory;
use tauri::{AppHandle, Manager, RunEvent, Url};
use tauri_plugin_shell::process::{CommandChild, CommandEvent};
use tauri_plugin_shell::ShellExt;

const READY_PREFIX: &str = "BRIEF_READY ";
const STARTUP_TIMEOUT: Duration = Duration::from_secs(60);

/// The running backend, so it can be stopped when the app quits.
#[derive(Default)]
struct Backend {
    child: Mutex<Option<CommandChild>>,
    quitting: AtomicBool,
}

/// Shows the bundled splash page in its error state.
fn show_error(app: &AppHandle, message: &str) {
    log::error!("{message}");
    let Some(window) = app.get_webview_window("main") else { return };
    let base = if cfg!(windows) { "http://tauri.localhost/" } else { "tauri://localhost/" };
    let mut url = Url::parse(base).expect("static URL");
    url.query_pairs_mut().append_pair("error", message);
    if let Err(err) = window.navigate(url) {
        log::error!("could not show the error page: {err}");
    }
}

fn start_backend(app: &AppHandle) -> Result<(), Box<dyn std::error::Error>> {
    let paths = app.path();
    let data_dir = paths.app_data_dir()?;
    let log_dir = paths.app_log_dir()?;
    let web_dir = paths.resolve("web", BaseDirectory::Resource)?;

    let (mut events, child) = app
        .shell()
        .sidecar("brief-api")?
        .args([
            "--port".into(),
            "0".into(),
            "--data-dir".into(),
            data_dir.to_string_lossy().into_owned(),
            "--log-dir".into(),
            log_dir.to_string_lossy().into_owned(),
            "--static-dir".into(),
            web_dir.to_string_lossy().into_owned(),
            "--parent-pid".into(),
            std::process::id().to_string(),
        ])
        .spawn()?;
    *app.state::<Backend>().child.lock().unwrap() = Some(child);

    let ready = Arc::new(AtomicBool::new(false));
    let log_hint = format!("Details are in {}", log_dir.join("backend.log").display());

    let handle = app.clone();
    let is_ready = ready.clone();
    let hint = log_hint.clone();
    tauri::async_runtime::spawn(async move {
        while let Some(event) = events.recv().await {
            match event {
                CommandEvent::Stdout(line) => {
                    let line = String::from_utf8_lossy(&line);
                    let Some(url) = line.trim().strip_prefix(READY_PREFIX) else { continue };
                    if is_ready.swap(true, Ordering::SeqCst) {
                        continue;
                    }
                    log::info!("backend ready at {url}");
                    match (Url::parse(url), handle.get_webview_window("main")) {
                        (Ok(url), Some(window)) => {
                            if let Err(err) = window.navigate(url) {
                                show_error(&handle, &format!("Could not open the app window: {err}"));
                            }
                        }
                        (Err(err), _) => show_error(&handle, &format!("The engine reported a bad address: {err}")),
                        (_, None) => {}
                    }
                }
                CommandEvent::Stderr(line) => {
                    log::warn!(target: "backend", "{}", String::from_utf8_lossy(&line).trim_end());
                }
                CommandEvent::Error(err) => log::error!(target: "backend", "{err}"),
                CommandEvent::Terminated(status) => {
                    is_ready.store(true, Ordering::SeqCst); // stops the startup timeout from firing too
                    if handle.state::<Backend>().quitting.load(Ordering::SeqCst) {
                        break;
                    }
                    let how = match status.code {
                        Some(code) => format!("stopped with exit code {code}"),
                        None => "was stopped".to_string(),
                    };
                    show_error(&handle, &format!("The analysis engine {how}. {hint}"));
                    break;
                }
                _ => {}
            }
        }
    });

    let handle = app.clone();
    tauri::async_runtime::spawn(async move {
        tokio::time::sleep(STARTUP_TIMEOUT).await;
        if !ready.load(Ordering::SeqCst) {
            show_error(&handle, &format!("The analysis engine didn't start within a minute. {log_hint}"));
        }
    });
    Ok(())
}

fn stop_backend(app: &AppHandle) {
    let backend = app.state::<Backend>();
    backend.quitting.store(true, Ordering::SeqCst);
    let child = backend.child.lock().unwrap().take();
    if let Some(child) = child {
        if let Err(err) = child.kill() {
            log::warn!("could not stop the backend: {err}");
        }
    }
}

/// Called by the splash page's "Restart" button.
#[tauri::command]
fn restart_app(app: AppHandle) {
    stop_backend(&app);
    app.restart();
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        // Must be registered first: a second launch just focuses the existing window.
        .plugin(tauri_plugin_single_instance::init(|app, _args, _cwd| {
            if let Some(window) = app.get_webview_window("main") {
                let _ = window.unminimize();
                let _ = window.show();
                let _ = window.set_focus();
            }
        }))
        .plugin(
            tauri_plugin_log::Builder::new()
                .level(log::LevelFilter::Info)
                .clear_targets()
                .target(tauri_plugin_log::Target::new(tauri_plugin_log::TargetKind::LogDir {
                    file_name: Some("app".into()),
                }))
                .target(tauri_plugin_log::Target::new(tauri_plugin_log::TargetKind::Stdout))
                .build(),
        )
        .plugin(tauri_plugin_window_state::Builder::default().build())
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_opener::init())
        .manage(Backend::default())
        .invoke_handler(tauri::generate_handler![restart_app])
        .setup(|app| {
            if !cfg!(debug_assertions) {
                if let Err(err) = start_backend(app.handle()) {
                    show_error(app.handle(), &format!("Could not start the analysis engine: {err}"));
                }
            }
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("error while building BriefLectures")
        .run(|app, event| {
            if let RunEvent::Exit = event {
                stop_backend(app);
            }
        });
}
