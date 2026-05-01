@echo off
cd /d "%~dp0"
echo Starting Cheers AI Agent server...
echo Open your browser at http://localhost:8000
echo Press Ctrl+C in this window to stop the server.
echo.
start "" http://localhost:8000
uv run python mcp_server.py
pause
