@echo off
setlocal

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0Start-Teddy.ps1" -AutoListen -EnableMouth
