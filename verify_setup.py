#!/usr/bin/env python3
"""
Verification script to check if the attendance system is properly set up
Run this after installing dependencies to verify everything works
"""

import sys
import os

def check_imports():
    """Check if all required modules can be imported"""
    print("Checking imports...")

    # Check core dependencies
    try:
        import cv2
        print(f"✓ OpenCV version: {cv2.__version__}")
    except ImportError as e:
        print(f"✗ OpenCV import failed: {e}")
        return False

    try:
        import numpy as np
        print(f"✓ NumPy version: {np.__version__}")
    except ImportError as e:
        print(f"✗ NumPy import failed: {e}")
        return False

    try:
        import flask
        print(f"✓ Flask version: {flask.__version__}")
    except ImportError as e:
        print(f"✗ Flask import failed: {e}")
        return False

    # Check face recognition dependencies
    try:
        import face_recognition
        print("✓ face_recognition imported successfully")
    except ImportError as e:
        print(f"✗ face_recognition import failed: {e}")
        print("  This usually means dlib is not installed properly")
        return False

    try:
        import face_recognition_models
        print("✓ face_recognition_models imported successfully")
    except ImportError as e:
        print(f"✗ face_recognition_models import failed: {e}")
        return False

    # Check our modules
    try:
        import face_recognition_utils
        print("✓ face_recognition_utils imported successfully")
    except ImportError as e:
        print(f"✗ face_recognition_utils import failed: {e}")
        return False

    try:
        import database_utils
        print("✓ database_utils imported successfully")
    except ImportError as e:
        print(f"✗ database_utils import failed: {e}")
        return False

    return True

def check_folders():
    """Check if required folders exist"""
    print("\nChecking folder structure...")

    folders = ['ImagesAttendance', 'templates']
    for folder in folders:
        if os.path.exists(folder):
            print(f"✓ Folder '{folder}' exists")
        else:
            print(f"✗ Folder '{folder}' missing - creating it")
            os.makedirs(folder, exist_ok=True)

    # Check for sample images
    images_folder = 'ImagesAttendance'
    if os.path.exists(images_folder):
        files = [f for f in os.listdir(images_folder)
                if f.lower().endswith(('.png', '.jpg', '.jpeg', '.webp'))]
        if files:
            print(f"✓ Found {len(files)} image(s) in ImagesAttendance")
        else:
            print(f"⚠ No images found in ImagesAttendance folder")
            print("  Add some student photos here for testing")
    else:
        print(f"✗ ImagesAttendance folder not found")

def check_files():
    """Check if required files exist"""
    print("\nChecking required files...")

    required_files = [
        'requirements.txt',
        'setup.py',
        'run.bat',
        'face_recognition_utils.py',
        'database_utils.py',
        'web_app.py',
        'main_project.py',
        'templates/index.html'
    ]

    missing = []
    for file in required_files:
        if os.path.exists(file):
            print(f"✓ {file}")
        else:
            print(f"✗ {file} - MISSING")
            missing.append(file)

    return len(missing) == 0

def main():
    """Main verification function"""
    print("=" * 50)
    print("Attendance System Setup Verification")
    print("=" * 50)

    # Check Python version
    print(f"Python version: {sys.version}")

    # Run checks
    imports_ok = check_imports()
    check_folders()
    files_ok = check_files()

    print("\n" + "=" * 50)
    if imports_ok and files_ok:
        print("✓ ALL CHECKS PASSED - System is ready to run!")
        print("\nNext steps:")
        print("1. Add student photos to ImagesAttendance folder")
        print("2. Run: python web_app.py")
        print("3. Open browser to http://localhost:5000")
    else:
        print("✗ SOME CHECKS FAILED - Please fix the issues above")
        if not imports_ok:
            print("\nFocus on installing missing dependencies first")
        if not files_ok:
            print("\nSome required files are missing")
    print("=" * 50)

if __name__ == "__main__":
    main()