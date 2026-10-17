@echo off
echo Starting Face Attendance System...
echo.
echo Make sure you have:
echo 1. Images in the 'ImagesAttendance' folder
echo 2. Python installed
echo 3. All requirements installed
echo.
echo Installing requirements...
pip install -r requirements.txt
echo.
echo Starting web application...
python web_app.py
pause 