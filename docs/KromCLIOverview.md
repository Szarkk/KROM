# Krom CLI Commands Overview

This document outlines the proposed command-line interface (CLI) for Krom, focusing on commands and flags to control features, stages, and enhancements. The CLI will be implemented in `krom/main.py` using Python's `argparse` library for parsing arguments. This allows for flexible, user-friendly control—e.g., enabling/disabling specific stages or add-ons without editing config files.

The design prioritizes:
- **Simplicity:** Basic runs with no flags (defaults to interactive wizard if no args, or all core stages enabled with enhancements disabled).
- **Modularity:** Flags for individual stages and enhancements.
- **Config Integration:** Override defaults with a YAML config file.
- **Safety:** Flags for dry runs, verbose logging, and backups.
- **Extensibility:** Support for custom parameters where needed (e.g., paths for secure wipe).

## Basic Usage
```
python main.py [flags] or python -m krom.main to start the interactive wizard
```
- Runs all enabled core stages in sequence by default if flags provided; triggers interactive wizard if no flags.
- Example: `python main.py --verbose` (runs defaults with detailed output).
- For bundled exe: `krom.exe [flags]`.

### Interactive Wizard
When running without flags (or with only globals like `--config`), Krom launches an interactive wizard for guided setup. This prompts step-by-step through global options, stage/enhancement selection, and custom parameters before running. Useful for casual users.

- **Navigation Commands (type at any prompt):**
  - `help`: Display wizard instructions and available commands.
  - `back`: Return to the previous question (redo your answer; limited to one step back for simplicity).
  - `end`: Quit the wizard and exit Krom without running.
  - `start`: Skip remaining prompts and begin the run with current selections (defaults for unanswered questions).
- Press Enter at a prompt to use the default (shown in parentheses, e.g., `(default: n)`).
- If you misanswer, use `back` to correct without restarting. The wizard saves progress until you exit or start.

Example flow:
- Global prompts (e.g., verbose, dry-run).
- Stage selection (e.g., comma-separated numbers or 'all').
- Enhancement selection (e.g., 'none' or numbers).
- Custom inputs (e.g., temp dirs).
- Summary review with "Looks good? (y/n)" before execution.

## Global Flags
These apply across the entire run.

| Flag | Description | Type/Default |
|------|-------------|--------------|
| `--config <path>` | Path to custom YAML config file (overrides defaults). | String (default: `./configs/default.yaml`) |
| `--verbose` | Enable detailed logging (console + file). | Boolean (default: False) |
| `--dry-run` | Simulate actions without changes (logs what would happen). | Boolean (default: False) |
| `--no-backup` | Skip backups (use with caution; not recommended). | Boolean (default: False) |
| `--safe-mode` | Run in safe mode (e.g., reboot prep if needed). | Boolean (default: False) |
| `--offline` | Enable offline mode: Skip network-dependent features (e.g., update checks in Patch stage). | Boolean (default: False) |
| `--help` | Show usage and all flags. | N/A |

## Stage-Specific Flags
Control core stages. By default, all are enabled. Use `--no-<stage>` to disable.

| Flag | Associated Stage | Description |
|------|------------------|-------------|
| `--prep` / `--no-prep` | Prep | Enable/disable backups, process killing, safe mode prep. |
| `--temp-clean` / `--no-temp-clean` | Temp Clean | Enable/disable temp file wiping. Add `--temp-dirs <dir1,dir2>` for custom paths. |
| `--de-bloat` / `--no-de-bloat` | De-Bloat | Enable/disable bloatware removal. Add `--bloat-list <file>` for custom app list. |
| `--disinfect` / `--no-disinfect` | Disinfect | Enable/disable malware scans. Add `--scan-tool <tool>` (e.g., clamav). |
| `--repair` / `--no-repair` | Repair | Enable/disable system fixes. |
| `--patch` / `--no-patch` | Patch | Enable/disable updates. Add `--offline-patches <dir>` for bundled patches. |
| `--optimize` / `--no-optimize` | Optimize | Enable/disable defrag/pagefile tweaks. |
| `--wrap-up` / `--no-wrap-up` | Wrap-Up | Enable/disable logs/reports. Add `--email-report <address>` for sending. |
| `--custom` / `--no-custom` | Custom | Enable/disable user plugins. Add `--plugins-dir <path>` (default: `./plugins`). |

Example: `python main.py --no-de-bloat --custom` (skips de-bloat, runs custom scripts).

## Enhancement-Specific Flags
Enhancements are disabled by default. Use `--<enhancement>` to enable.

| Flag | Associated Enhancement/Stage | Description |
|------|------------------------------|-------------|
| `--cloud-backup` | Cloud Backup Integration (Prep) | Enable cloud backups. Requires `--cloud-provider <dropbox/google>` and `--auth-token <token>`. |
| `--browser-cleanup` | Browser Cleanup (Temp Clean) | Enable browser-specific cleaning. Add `--browsers <chrome,firefox>` to target. |
| `--privacy-scrub` | Privacy Scrub (After De-Bloat) | Enable privacy tweaks. Add `--hosts-file <path>` for custom blocks. |
| `--uninstall-residue` | Uninstall Residue Remover (After De-Bloat) | Enable residue hunting. |
| `--driver-audit` | Driver Audit (After Repair) | Enable driver checks. Add `--suggest-updates` to list recommendations. |
| `--startup-manager` | Startup Manager (During Optimize) | Enable startup auditing. Add `--interactive` for user review menu. |
| `--benchmark-report` | Benchmark & Report (Wrap-Up) | Enable before/after benchmarks. Add `--visualize` for charts. |
| `--scheduled-mode` | Scheduled Mode (Post-Run) | Enable scheduling prompt. Add `--frequency <weekly/daily>` for auto-setup. |
| `--hardware-health` | Hardware Health Check (Diagnostics) | Enable hardware scans. Run as standalone with `--standalone-hardware`. |
| `--secure-wipe` | Secure Wipe (Pre-Run/Standalone) | Enable secure deletion. Requires `--wipe-paths <file1,dir2>`. Run standalone with `--standalone-wipe`. |

Example: `python main.py --privacy-scrub --benchmark-report` (runs core stages + these enhancements).

## Advanced/Standalone Modes
For running specific features independently (useful for testing or targeted use):
- `--standalone <stage/enhancement>`: Run only that stage/enhancement (e.g., `--standalone hardware-health`).
- This skips the full sequence but still applies global flags. **Note:** Not all stages/enhancements work fully standalone—prerequisites (e.g., Prep for Temp Clean to unlock files) may cause reduced effectiveness or warnings (e.g., "Recommend Prep before Temp Clean"). Combine with prior stages (e.g., `--standalone temp_clean --prep`) or enable backups explicitly for safety.

## Config File Integration
- If no flags are provided for a stage/enhancement, fall back to the config file. Users can edit `./configs/default.yaml` for persistent settings, or pass a custom one via `--config`.
- For per-tool keep options, edit config YAML.

## Implementation Notes
- In `main.py`, use `argparse.ArgumentParser()` to define these flags.
- Group flags with `add_argument_group()` for better `--help` output (e.g., "Global", "Stages", "Enhancements").
- Parse args, merge with config (using `pyyaml`), then dispatch to stages.
- For flags with values, use `type=str` or `nargs='+'` as needed.
- Error handling: Validate conflicts and prerequisites (e.g., warn if `--standalone temp_clean` without `--prep`; implement in main.py dispatcher).