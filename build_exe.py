#!/usr/bin/env python3
"""
Build script to create executable using PyInstaller
Run this script to build the LLaMA Server GUI executable
"""

import PyInstaller.__main__
import os
import sys

def build_executable():
    """Build the executable using PyInstaller"""
    
    # Define the build arguments
    args = [
        'llama-server_gui_new.py',              # Main script
        '--onedir',                     # Create directory mode (no temp dir, no cleanup warning)
        '--windowed',                   # No console window (GUI app)
        '--name=LLaMA-Server-GUI',      # Name of the executable
        '--icon=llama-cpp.ico',         # Icon file (if exists)
        '--add-data=llama-cpp.ico;.',   # Include icon in bundle (Windows format)
        '--clean',                      # Clean before building
        '--noconfirm',                  # Overwrite without asking
        # Add hidden imports if needed
        '--hidden-import=tkinter',
        '--hidden-import=tkinter.ttk',
        '--hidden-import=tkinter.filedialog',
        '--hidden-import=tkinter.messagebox',
        '--hidden-import=tkinter.scrolledtext',
        '--hidden-import=tkinter.font',
    ]
    
    # On Linux/Mac, use colon separator for add-data
    if sys.platform != 'win32':
        # Replace Windows path separator with Unix
        for i, arg in enumerate(args):
            if arg.startswith('--add-data='):
                args[i] = arg.replace(';', ':')
    
    print("Building executable with PyInstaller...")
    print(f"Arguments: {' '.join(args)}")
    
    try:
        PyInstaller.__main__.run(args)
        print("\n✅ Build completed successfully!")
        print("📁 Check the 'dist' folder for your executable")
        
        # Print the location of the executable
        if sys.platform == 'win32':
            exe_name = "LLaMA-Server-GUI.exe"
        else:
            exe_name = "LLaMA-Server-GUI"
            
        exe_path = os.path.join("dist", exe_name)
        if os.path.exists(exe_path):
            print(f"📄 Executable created: {exe_path}")
        
    except Exception as e:
        print(f"❌ Build failed: {e}")
        return False
    
    return True

if __name__ == "__main__":
    # Check if PyInstaller is installed
    try:
        import PyInstaller
        print(f"PyInstaller version: {PyInstaller.__version__}")
    except ImportError:
        print("❌ PyInstaller not found. Install it with: pip install pyinstaller")
        sys.exit(1)
    
    # Check if main script exists
    if not os.path.exists("llama-server_gui_new.py"):
        print("❌ llama-server_gui_new.py not found in current directory")
        sys.exit(1)
    
    # Build the executable
    success = build_executable()
    
    if success:
        print("\n🎉 Your LLaMA Server GUI is ready to use!")
        print("💡 You can distribute the executable without requiring Python installation")
    else:
        print("\n💥 Build failed. Check the error messages above.")
        sys.exit(1)