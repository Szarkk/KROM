# KROM Project Architecture

This document outlines the recommended directory structure and overall architecture for the KROM project. KROM is a modular, Python-based deep cleaning tool for Windows, inspired by TronScript, designed for extensibility, safety, and ease of maintenance. The structure follows standard Python best practices (e.g., inspired by PEP 8 and common open-source layouts) while accommodating the staged workflow from the features overview.

The architecture emphasizes:
- **Modularity:** Each core stage and enhancement is in its own module or script, importable via the main entry point.
- **Configuration:** Use a YAML config file for toggles, paths, and user preferences.
- **Safety:** Backups and logs are centralized, with dry-run modes and error handling.
- **Extensibility:** Plugins directory for custom additions.
- **Testing:** Dedicated folder for unit/integration tests.
- **Deployment:** Root-level scripts for building (e.g., PyInstaller) and a `dist/` folder for output artifacts.

We'll use Python 3.x as the primary language. For cross-platform compatibility, avoid OS-specific paths where possible (use `pathlib`). Bundle the project into a standalone executable for distribution. Repo URL: https://github.com/Szarkk/KROM.git (private for now; toggle public later).

## Directory Structure

Here's the proposed tree structure (updated with recent additions like PyInstaller spec, report handling, and data/ for static assets like YARA rules):

KROM/                           # Project root (open this as your VS Code workspace)
├── .copilot/                   # VS Code Copilot/Grok instructions (local, ignored)
│   └── instructions.md         # Guidelines for AI assistance (e.g., safety rules)
├── .gitignore                  # Root ignores for builds, logs, caches (see below)
├── dist/                       # Distribution folder (e.g., for built executables, installers)
│   └── .gitignore              # Sub-ignores for artifacts (e.g., *.exe, *.msi)
├── krom/                       # Main package (for importability)
│   ├── init.py             # Package init (version, imports)
│   ├── main.py                 # Entry point: CLI parser, stage orchestration
│   ├── config.py               # Config loader (YAML parsing, defaults)
│   ├── logger.py               # Centralized logging setup
│   ├── data/                   # NEW: Static assets (YARA rules, hash lists, etc.)
│   │   ├── pup_rules.yar       # Heuristic rules for disinfect stage
│   │   ├── known_bad_hashes.txt # List of SHA256 hashes (load in config)
│   │   └── README.md           # Usage notes for adding rules/hashes
│   ├── stages/                 # Core stages as modules
│   │   ├── init.py
│   │   ├── prep.py             # Prep stage logic (backups, process kill)
│   │   ├── temp_clean.py       # Temp clean stage
│   │   ├── de_bloat.py         # De-bloat stage
│   │   ├── disinfect.py        # Disinfect stage (AV scan)
│   │   ├── repair.py           # Repair stage
│   │   ├── patch.py            # Patch stage (offline mode)
│   │   ├── optimize.py         # Optimize stage
│   │   ├── wrap_up.py          # Wrap-up stage
│   │   └── custom.py           # Custom scripts executor
│   ├── enhancements/           # Add-ons as modules (import and call if enabled)
│   │   ├── init.py
│   │   ├── browser_cleanup.py
│   │   ├── privacy_scrub.py
│   │   ├── uninstall_residue.py
│   │   ├── driver_audit.py
│   │   ├── startup_manager.py
│   │   ├── benchmark_report.py
│   │   ├── scheduled_mode.py
│   │   ├── hardware_health.py
│   │   └── secure_wipe.py
│   └── utils/                  # Reusable utilities
│       ├── init.py
│       ├── backup.py           # Backups (registry/files, restore)
│       ├── file_ops.py         # File operations (shutil wrappers)
│       ├── metrics.py          # Performance metrics (psutil)
│       ├── network.py          # Network checks (offline mode)
│       └── system.py           # System commands (subprocess, admin check)
├── plugins/                    # User plugins (scanned by custom.py)
│   └── README.md               # Plugin guidelines
├── configs/                    # Configuration files
│   └── default.yaml            # Default toggles/paths (stages, enhancements)
├── tests/                      # Tests (pytest)
│   ├── init.py
│   ├── test_stages.py          # Stage tests (mocks for subprocess)
│   ├── test_enhancements.py    # Enhancement tests
│   └── test_utils.py           # Utils tests (e.g., backup mocks)
├── docs/                       # Documentation (ignored, local)
│   ├── KromFeaturesOverview.md
│   ├── KromCLIOverview.md
│   └── KromProjectArchitecture.md  # This file
├── build_exe.py                # PyInstaller build script (--distpath dist)
├── krom.spec                   # PyInstaller spec file (generated/edited)
├── requirements.txt            # Dependencies (psutil, pyyaml, tqdm, etc.)
├── setup.py                    # Packaging (setuptools for installable package)
├── README.md                   # Project overview, install/run instructions
├── LICENSE                     # License file
└── krom_report.txt             # Runtime report (ignored, generated by wrap_up.py)


#### Files Explained
- **krom/main.py:** The heart of the app. Parses CLI args (e.g., using `argparse`), loads config, runs stages in sequence. Example flow: Prep → Temp Clean → ... → Wrap-Up. Enhancements are injected into associated stages (e.g., Privacy Scrub after De-Bloat).
- **dist/:** Folder for deployment outputs, like the built `krom.exe` from PyInstaller. Update `build_exe.py` to target this dir (e.g., `--distpath dist`).
- **krom/data/:** NEW: Houses static files for heuristics (e.g., YARA rules loaded in disinfect.py). Keeps configs lean; add rules/hashes here for easy user extension.
- **krom/utils/run.bat:** A simple batch file for easy Windows launches. Example content: `@echo off\npython krom\main.py %*` or point to the exe in `dist/`. This makes running KROM one-click for users.
- **Stages and Enhancements:** Each module exports a function like `run_stage(args, config, logger)` for consistency. Use decorators or hooks for pre/post actions (e.g., backups).
- **Utils:** Reusable code to avoid duplication. For example, `backup.py` handles registry exports and file copies. The `run.bat` here is for quick execution from the utils dir.
- **Plugins:** In `custom.py`, scan the `plugins/` dir and execute files if enabled. Support safe execution (e.g., in subprocess).
- **Logging:** Use Python's `logging` module with file+console handlers. Verbose mode via flag.
- **Testing:** Use `pytest` for tests. Mock system calls to avoid real changes during tests.
- **GUI Option:** If adding Tkinter, put it in `krom/gui.py` as an optional wrapper around `main.py`.
- **Deployment:** `build_exe.py` script: `pyinstaller --onefile main.py --name krom.exe --distpath dist`. Generate `krom.spec` for custom builds (e.g., include data files).
- **Reports:** `krom_report.txt` generated by `wrap_up.py`—ignore in `.gitignore` to avoid versioning runtime data.

### Architectural Principles
- **Workflow:** Sequential stages with hooks for enhancements. Use a dispatcher in `main.py` to run only enabled parts.
- **Error Handling:** Wrap each stage in try-except, log errors, and offer rollback (using backups).
- **Cross-Platform:** Use `platform` module to detect OS; focus on Windows but stub Linux/Mac support.
- **Dependencies:** Keep minimal: `psutil`, `pyyaml`, `matplotlib`, `subprocess`, `winreg` (Windows-only), etc. No heavy frameworks unless needed. List in `requirements.txt`.
- **Security:** Run as admin only when necessary (prompt via code). Avoid auto-installing anything risky.
- **Portfolio Tips:** Include diagrams (e.g., Mermaid flowcharts in README) showing stage flow. Comment code heavily. Use VS Code with `.copilot/instructions.md` for Grok-assisted dev.

This structure is flexible—start with core stages, add enhancements iteratively.