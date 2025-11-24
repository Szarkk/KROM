# Krom Data Directory

This directory holds static assets for Krom's heuristics and detection logic, loaded dynamically in stages like `disinfect.py`. Keeps configs lean and rules extensible—users can add/update without code changes.

## Files
- **pup_rules.yar**: YARA rules for PUPs/malware (e.g., adware droppers, RATs). Compiled via `yara.compile()` in heuristics. Add rules here (MIT license; see header for sources).
- **known_bad_hashes.txt**: Line-delimited SHA256 hashes for fallback detection (if YARA skips). Loaded as list in `default.yaml`.
- **Future Assets**: e.g., `browser_extensions_blacklist.json` for enhancements, or `bloatware_list.csv` for de_bloat.

## Guidelines
- **Adding Rules/Hashes**: Append to files (no duplicates). Test with sample malware (e.g., EICAR test file in `%TEMP%`).
- **Validation**: Run `yara -p pup_rules.yar test_file.exe` in terminal to verify syntax.
- **Sources**: Pull from awesome-yara (GitHub), Abuse.ch, or VMRay for fresh sigs. Update quarterly.
- **Integration**: Paths in `default.yaml` (e.g., `rules_path: './data/pup_rules.yar'`). Logs skips if missing.

For issues, see `docs/` or open a GitHub issue.