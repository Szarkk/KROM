# KROM: Modular Windows Deep Cleaning Tool Framework

**A safe, modular, fully-commented Python learning project for anyone who wants to understand Windows automation.**

KROM started as my personal “TronScript-inspired” deep cleaner.  
After months of building stages, backups, a CLI wizard, and a ton of safety features, I realized something:

This code is now way more useful as a **teaching tool** than as yet another cleanup script.

So I’m graduating it.

### Why this exists now
- Every stage is deliberately over-commented and split into tiny, readable functions  
- Real safety is baked in (backups, dry-run, admin checks, rollback stubs) – perfect for learning how to script without bricking your PC  
- Config-driven everything (default.yaml) so you can tweak behavior without touching code  
- Interactive wizard + argparse CLI shows two real-world ways to build user-friendly tools  
- Zero internet-required dependencies (just psutil, pyyaml, tqdm) – runs anywhere  
- Clear folder structure (stages/, enhancements/, utils/) that teaches clean project layout

### Perfect for
- Students learning Python on Windows  
- People studying for CompTIA A+/Security+ who want hands-on scripting experience  
- Hobbyists who want to fork and add their own stages  
- Anyone who ever googled “how do I safely delete temp files with Python?”

### How to use it as a learning project
1. Fork → clone → run `python main.py` (or the built .exe)  
2. Read the comments in any stage (start with `prep.py` or `temp_clean.py`)  
3. Try the beginner challenges in CONTRIBUTING.md  
4. Break something on purpose → learn how the backup/restore system saves you  
5. Add your own stage or enhancement and open a PR (I’ll merge good ones!)

KROM is now officially a **baseline / starter-kit**.  
I’m stepping away from active development, but the repo stays public forever for anyone who wants to learn, experiment, or teach with it.

Feel free to use it in your portfolio, your classroom, or just to mess around safely.

– Szarkk  
(November 2025)
