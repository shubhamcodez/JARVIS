# JARVIS Calculator

A simple desktop calculator built with [Tauri 2](https://v2.tauri.app/) (Rust + HTML/CSS/JS).

## Prerequisites

- **Node.js** (v18 or later) – [nodejs.org](https://nodejs.org/)
- **Rust** – [rustup.rs](https://rustup.rs/) (install and then restart your terminal)
- **Windows:** Visual Studio Build Tools or `winget install Microsoft.VisualStudio.2022.BuildTools` (needed to compile Rust on Windows)

## Run in development

```bash
cd E:\JARVIS
npm install
npm run dev
```

The first `npm run dev` will compile the Rust side (may take a few minutes). The calculator window should open.

## Build for production

```bash
npm run build
```

The executable will be in `src-tauri/target/release/` (or `target/release/jarvis_calculator.exe` on Windows).

## Optional: custom app icon

To use your own icon:

```bash
npm run tauri icon path/to/your-icon.png
```

Then build again. Without this, the app uses default Tauri branding.

## Project layout

| Path | Purpose |
|------|--------|
| **Frontend** | |
| `frontend/index.html` | Calculator UI structure |
| `frontend/style.css` | Layout and styling |
| `frontend/calculator.js` | UI logic, calls backend via Tauri `invoke` |
| **Backend** | |
| `src-tauri/` | Rust app: window, config, Tauri shell |
| `src-tauri/src/main.rs` | Rust entry point and `calculate` command |

## Learning Rust along the way

- **`main.rs`** – The only Rust file we use so far. It builds the Tauri app and runs it. You can change the window title or size in `src-tauri/tauri.conf.json` without touching Rust.
- When you’re ready, try adding a [Tauri command](https://v2.tauri.app/develop/calling-rust/) (a Rust function) and call it from JavaScript – that’s the usual way to add Rust logic to a Tauri app.
