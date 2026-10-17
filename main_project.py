"""
Main attendance system application (Desktop version)
Refactored to use optimized modular components for better performance
"""
import cv2
from face_recognition_utils import (
    FaceRecognitionOptimizer,
    draw_face_boxes,
    add_timestamp_to_frame
)
from database_utils import AttendanceDatabaseOptimized


def main():
    """Main function to run the desktop attendance system"""
    print("Loading optimized face recognition system...")

    # Initialize face recognition optimizer (loads pre-computed embeddings or computes them)
    # Try to use GPU if available
    face_optimizer = FaceRecognitionOptimizer('ImagesAttendance', use_gpu=True)

    # Show stats
    stats = face_optimizer.get_stats()
    print(f"Face recognition stats: {stats}")

    # Initialize database
    db = AttendanceDatabaseOptimized()
    # We'll pass face names to database for status reporting via a callback or property
    # For now, we'll set it directly (in practice, you might want a cleaner approach)
    db.face_names = face_optimizer.known_face_names if face_optimizer.known_face_names else []

    # Initialize webcam
    cap = cv2.VideoCapture(0)

    print("Starting optimized attendance system. Press 'q' to quit.")

    while True:
        success, img = cap.read()
        if not success:
            print("Failed to capture image from webcam")
            break

        img = cv2.flip(img, 1)

        # Process frame for face recognition
        face_locations, face_encodings = face_optimizer.find_face_locations_and_encodings(img)

        if face_encodings:
            # Recognize faces using optimized search
            recognized_names = face_optimizer.recognize_faces_optimized(face_encodings)

            # Mark attendance for recognized faces
            for name in recognized_names:
                if name:  # Only process if a face was recognized
                    db.mark_attendance(name)

            # Draw face boxes and names
            img = draw_face_boxes(img, face_locations, recognized_names)

        # Add timestamp to frame
        img = add_timestamp_to_frame(img)

        # Display the frame
        cv2.imshow('webcam', img)

        # Break loop on 'q' key press
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    # Cleanup
    cap.release()
    cv2.destroyAllWindows()
    print("Attendance system stopped.")


if __name__ == "__main__":
    main()