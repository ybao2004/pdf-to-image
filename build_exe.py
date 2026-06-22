import os
import subprocess
import sys
import re

def run_cmd(cmd):
    print(f"Running: {cmd}")
    subprocess.run(cmd, shell=True, check=True)

# 1. Parse version from pdf-to-image.py
print("Parsing APP_VERSION from pdf-to-image.py...")
with open("pdf-to-image.py", "r", encoding="utf-8") as f:
    content = f.read()

match = re.search(r'APP_VERSION\s*=\s*"([^"]+)"', content)
if not match:
    print("Error: Could not find APP_VERSION in pdf-to-image.py")
    sys.exit(1)
app_version = match.group(1)
print(f"Found version: {app_version}")

# 2. Update setup.iss
print("Updating setup.iss...")
with open("setup.iss", "r", encoding="utf-8") as f:
    iss_content = f.read()

# Replace the #define AppVer line
iss_content = re.sub(r'#define AppVer.*', f'#define AppVer "{app_version}"', iss_content)
with open("setup.iss", "w", encoding="utf-8") as f:
    f.write(iss_content)

print("1. Creating virtual environment...")
# run_cmd("python -m venv build_env")

print("2. Installing core dependencies...")
python_exe = os.path.join("build_env", "Scripts", "python")
run_cmd(f"{python_exe} -m pip install PyQt6 PyMuPDF Pillow psutil pyinstaller")

print("3. Building executable with PyInstaller...")
pyinstaller_exe = os.path.join("build_env", "Scripts", "pyinstaller")
target_script = "pdf-to-image.py"
excludes = "--exclude-module PyQt6.QtQml --exclude-module PyQt6.QtSql --exclude-module PyQt6.QtTest --exclude-module PyQt6.QtXml --exclude-module PyQt6.QtOpenGL --exclude-module PyQt6.QtOpenGLWidgets --exclude-module PyQt6.QtWebEngineCore --exclude-module PyQt6.QtWebEngineWidgets --exclude-module tkinter --exclude-module matplotlib"
run_cmd(f"{pyinstaller_exe} {excludes} --noconfirm --windowed --clean --icon=app_icon.ico --add-data \"app_icon.ico;.\" --add-data \"app_icon.png;.\" --name \"PDF to Image\" \"{target_script}\"")

print("4. Building Inno Setup Installer...")
iscc_path = os.path.join(os.environ["LOCALAPPDATA"], "Programs", "Inno Setup 6", "ISCC.exe")
if os.path.exists(iscc_path):
    run_cmd(f'"{iscc_path}" setup.iss')
    print("Done! Setup executable is in the 'Output' folder.")
else:
    print("ISCC.exe not found. Skipping Inno Setup build.")

