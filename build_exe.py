import subprocess
import sys
import os

def build_exe():
    """
    Build Krom into a standalone executable using PyInstaller.
    Outputs to dist/ folder as krom.exe (onefile mode for portability).
    Run this from the project root.
    """
    # Ensure PyInstaller is installed
    try:
        print("Installing PyInstaller if needed...")
        subprocess.check_call([sys.executable, '-m', 'pip', 'install', 'pyinstaller'])
    except subprocess.CalledProcessError as e:
        print(f"PyInstaller installation failed: {e}")
        print("Install manually: pip install pyinstaller")
        return 1

    # Test import
    try:
        import PyInstaller
        print("PyInstaller import successful!")
    except ImportError:
        print("PyInstaller still not importable—manual install needed.")
        return 1

    # PyInstaller command: Build from project root, entry as krom/main.py (module mode)
    # This auto-includes package submodules like stages/*
    cmd = [
        sys.executable, '-m', 'PyInstaller',
        '--onefile',
        '--collect-all', 'krom',  # <-- bundles entire krom package recursively
        '--name', 'krom',
        '--distpath', 'dist',  # Output to dist/ in project root (simpler)
        '--add-data', 'configs;configs',  # Include configs folder
        'krom/main.py'  # Entry point as module path from root
    ]

    print(f"Running: {' '.join(cmd)}")
    try:
        result = subprocess.run(cmd, check=True)  # No cwd—run from project root
        print("Build successful! Check dist/krom.exe")
        return 0
    except subprocess.CalledProcessError as e:
        print(f"Build failed: {e}")
        return 1

if __name__ == '__main__':
    sys.exit(build_exe())