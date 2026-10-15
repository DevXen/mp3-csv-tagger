@echo off
rem Build a standalone 64-bit Windows program: dist\MP3CsvTagger\MP3CsvTagger.exe
rem Run from the repo root on Windows with Python 3.10+ on PATH.
setlocal
python -m venv .build-venv
call .build-venv\Scripts\activate.bat
pip install --upgrade pip
pip install . pyinstaller
pyinstaller --noconfirm mp3csvtagger.spec
echo.
echo Done: dist\MP3CsvTagger\MP3CsvTagger.exe
endlocal
