# KROM: Modular Windows Deep Cleaning Tool Framework

**A safe, modular, fully-commented Python learning project for anyone who wants to understand Windows automation.**

KROM started as my personal “TronScript-inspired” deep cleaner.  
After weeks of building a full-featured Windows deep-cleaning tool (backups, dry-run, wizard, stages, the works), I’ve decided to turn it into exactly what it’s best at:

An open, over-commented, super-safe Python learning project for anyone getting into Windows automation.

### Why this exists now
- Every stage is deliberately over-commented and split into tiny, readable functions  
- Real safety is baked in (backups, dry-run, admin checks, rollback stubs) – perfect for learning how to script without bricking your PC  
- Config-driven everything (default.yaml) so you can tweak behavior without touching code  
- Interactive wizard + argparse CLI shows two real-world ways to build user-friendly tools  
- Zero internet-required dependencies (just psutil, pyyaml, tqdm) – runs anywhere  
- Clear folder structure (stages/, enhancements/, utils/) that teaches clean project layout

### Perfect for
- Students learning Python on Windows
- Students who need a concrete, real-world Python project for their portfolio that isn’t another TODO app
- People studying for CompTIA A+/Security+ who want hands-on scripting experience  
- Hobbyists who want to fork and add their own stages  
- Anyone who believes learning by reading + breaking + fixing real code beats yet another YouTube tutorial

### How to use it as a learning project
1. Fork → clone → run `python -m krom.main` on PowerShell or Terminal (Admin)
2. Read the comments in any stage (start with `prep.py` or `temp_clean.py`)  
3. Break something on purpose (on an old and unused computer, not your main) → learn how the backup/restore system saves you  
4. Add your own stage or enhancement

KROM is a **baseline / starter-kit**.  
I'd still be slowly updating this, stepping away from active developmen, but the repo stays public forever for anyone who wants to learn, experiment, or teach with it. Or even make it better.

Feel free to use it in your portfolio, your classroom, or just to mess around safely.

– Szarkk  
(November 2025)

Note: the build .exe is outdated.
