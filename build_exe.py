#!/usr/bin/env python3
"""
Build script to create executable using PyInstaller

Usage:
    python build_exe.py              # default: --onedir (directory mode)
    python build_exe.py --onefile    # single-file executable
    python build_exe.py --name=MyApp # custom name
"""

import PyInstaller.__main__
import os
import sys
import argparse


def build_executable(onefile=False, name="LLaMA-Server-GUI"):
    """Build the executable using PyInstaller"""

    mode = "onefile" if onefile else "onedir"

    args = [
        'llama-server_gui_new.py',
        f'--{mode}',
        '--windowed',
        f'--name={name}',
        '--icon=llama-cpp.ico',
        '--add-data=llama-cpp.ico;.',
        '--clean',
        '--noconfirm',
        '--hidden-import=tkinter',
        '--hidden-import=tkinter.ttk',
        '--hidden-import=tkinter.filedialog',
        '--hidden-import=tkinter.messagebox',
        '--hidden-import=tkinter.scrolledtext',
        '--hidden-import=tkinter.font',
    ]

    # On Linux/Mac, use colon separator for add-data
    if sys.platform != 'win32':
        args = [arg.replace(';', ':') if arg.startswith('--add-data=') else arg for arg in args]

    print(f"Building {mode} executable with PyInstaller...")
    print(f"Args: {' '.join(args)}")

    try:
        PyInstaller.__main__.run(args)
        print("\n Build completed successfully!")

        if onefile:
            if sys.platform == 'win32':
                exe_path = os.path.join("dist", f"{name}.exe")
            else:
                exe_path = os.path.join("dist", name)
        else:
            exe_path = os.path.join("dist", name)

        if os.path.exists(exe_path):
            print(f" Executable created: {exe_path}")
    except Exception as e:
        print(f" Build failed: {e}")
        return False

    return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build LLaMA Server GUI executable")
    parser.add_argument('--onefile', action='store_true',
                        help="Build as single-file executable (default: directory mode)")
    parser.add_argument('--name', default="LLaMA-Server-GUI",
                        help="Executable name (default: LLaMA-Server-GUI)")
    args = parser.parse_args()

    try:
        import PyInstaller
        print(f"PyInstaller version: {PyInstaller.__version__}")
    except ImportError:
        print(" PyInstaller not found. Install it with: pip install pyinstaller")
        sys.exit(1)

    if not os.path.exists("llama-server_gui_new.py"):
        print(" llama-server_gui_new.py not found in current directory")
        sys.exit(1)

    success = build_executable(onefile=args.onefile, name=args.name)

    if success:
        print("\n Your LLaMA Server GUI is ready to use!")
        if args.onefile:
            print(" Single-file executable created (dist/)")
        else:
            print(" Executable directory created (dist/)")
    else:
        print("\n Build failed. Check the error messages above.")
        sys.exit(1)
