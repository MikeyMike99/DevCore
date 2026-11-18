@echo off
rem Compiles the lab kit into ONE exe the learner can double-click. No Docker/WSL/Python needed on their PC.
cd /d "%~dp0"
python -m unittest discover -s tests || exit /b 1
python -m nuitka --onefile --include-package=siraugga_lab --include-data-dir=siraugga_lab\labs=siraugga_lab\labs ^
  --output-filename=siraugga-lab.exe --output-dir=dist --assume-yes-for-downloads --company-name=Siraugga ^
  --product-name="Siraugga Lab" --file-version=0.1.0 siraugga_lab\__main__.py
