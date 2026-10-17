import os
import subprocess
import sys

def install_requirements():
    print("Installing requirements...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])

def create_directories():
    if not os.path.exists('ImagesAttendance'):
        os.makedirs('ImagesAttendance')
        print("Created ImagesAttendance folder. Please add your face images here.")
    
    if not os.path.exists('templates'):
        os.makedirs('templates')
        print("Created templates folder.")

if __name__ == "__main__":
    print("Setting up Face Attendance System...")
    create_directories()
    install_requirements()
    print("Setup complete! Run 'python web_app.py' to start the system.") 