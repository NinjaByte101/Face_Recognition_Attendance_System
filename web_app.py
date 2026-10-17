"""
Web-based attendance system using Flask
Refactored to use optimized modular components for better performance
"""
from flask import Flask, render_template, Response, jsonify, make_response, request
import cv2
import threading
from queue import Queue
import time
import datetime
import csv
import os
from face_recognition_utils import (
    FaceRecognitionOptimizer,
    add_timestamp_to_frame
)
from database_utils import AttendanceDatabaseOptimized


app = Flask(__name__)

# Initialize optimized components
print("Loading optimized face recognition system...")
face_optimizer = FaceRecognitionOptimizer('ImagesAttendance', use_gpu=True)
print(f"Faces loaded successfully! Loaded {len(face_optimizer.known_face_names)} faces")

# Initialize database and set face names for status reporting
db = AttendanceDatabaseOptimized()
db.face_names = face_optimizer.known_face_names if face_optimizer.known_face_names else []

# Threading components for video processing
camera = None
attendance_lock = threading.Lock()
_csv_write_queue: Queue[bool] = Queue(maxsize=1)
frame_count = 0
current_recognized = set()
last_notice_message = ''
last_notice_ts = 0.0
COOLDOWN_SECONDS = 4

def today_date_str(ts=None):
    """Get today's date string in DD-MM-YYYY format"""
    if ts is None:
        ts = time.time()
    return datetime.fromtimestamp(ts).strftime('%d-%m-%Y')

def _write_csv_sync():
    """Synchronously write attendance data to CSV"""
    with attendance_lock:
        tmp = 'Attendance.csv' + '.tmp'
        with open(tmp, 'w', newline='') as f:
            writer = csv.writer(f)
            for rec in db.attendance_data:
                writer.writerow([rec['name'], rec['date'], rec['punch_in'], rec['punch_out']])
        os.replace(tmp, 'Attendance.csv')

def _csv_writer_worker():
    """Background worker for CSV writing"""
    while True:
        try:
            _csv_write_queue.get()
            _write_csv_sync()
        except Exception:
            pass

# Start CSV writer thread
t = threading.Thread(target=_csv_writer_worker, daemon=True)
t.start()


class ThreadedCamera:
    def __init__(self, src=0, width=640, height=480):
        self.cap = cv2.VideoCapture(src, cv2.CAP_DSHOW)
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        self.lock = threading.Lock()
        self.running = True
        self.ret = False
        self.frame = None
        t = threading.Thread(target=self._reader, daemon=True)
        t.start()

    def _reader(self):
        while self.running:
            ret, frame = self.cap.read()
            if not ret:
                time.sleep(0.02)
                continue
            with self.lock:
                self.ret = ret
                self.frame = frame

    def read(self):
        with self.lock:
            return self.ret, self.frame.copy() if self.frame is not None else (False, None)

    def release(self):
        self.running = False
        try:
            self.cap.release()
        except:
            pass


def init_camera():
    """Initialize or return existing camera instance"""
    global camera
    if camera is None:
        camera = ThreadedCamera(src=0, width=640, height=480)
    return camera


def generate_frames():
    """Generate video frames for streaming"""
    global frame_count, current_recognized, last_notice_message, last_notice_ts
    cam = init_camera()
    frame_count = 0

    while True:
        success, img = cam.read()
        if not success or img is None:
            time.sleep(0.01)
            continue

        img = cv2.flip(img, 1)
        frame_count += 1

        # Process every 2nd frame for face recognition (performance optimization)
        if len(face_optimizer.known_face_embeddings) > 0 and frame_count % 2 == 0:
            face_locations, face_encodings = face_optimizer.find_face_locations_and_encodings(img)

            if face_encodings:
                # Recognize faces using optimized search
                recognized_names = face_optimizer.recognize_faces_optimized(face_encodings)
                new_recognized = set()

                # Process recognized faces
                for _, faceLoc, name in zip(face_encodings, face_locations, recognized_names):
                    if name:  # Only process if a face was recognized
                        # Mark attendance with cooldown
                        current_time = time.time()
                        last_time = db.last_attendance.get(name, 0)
                        if current_time - last_time < COOLDOWN_SECONDS:
                            pass  # Still in cooldown, don't mark attendance
                        else:
                            if db.mark_attendance(name):
                                new_recognized.add(name)

                                # Draw face box and label
                                y1, x2, y2, x1 = faceLoc
                                y1, x2, y2, x1 = y1*4, x2*4, y2*4, x1*4
                                cv2.rectangle(img, (x1, y1), (x2, y2), (0, 200, 0), 2)
                                cv2.rectangle(img, (x1, y2-30), (x2, y2), (0, 200, 0), cv2.FILLED)
                                cv2.putText(img, name, (x1+6, y2-6), cv2.FONT_HERSHEY_COMPLEX, 0.9, (255, 255, 255), 2)
                    # else: unknown face, don't add to recognized set

                current_recognized = new_recognized

        # Display currently recognized names
        if len(current_recognized) > 0:
            y = 50
            for n in current_recognized:
                cv2.putText(img, n, (10, y), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
                y += 28

        # Add timestamp to frame
        img = add_timestamp_to_frame(img)

        # Display cooldown notice if active
        now_ts = time.time()
        if last_notice_ts and (now_ts - last_notice_ts) <= 5:
            cv2.putText(img, last_notice_message, (10, img.shape[0] - 20),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)

        # Encode frame as JPEG
        ret, buffer = cv2.imencode('.jpg', img)
        if not ret:
            time.sleep(0.01)
            continue

        frame = buffer.tobytes()
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')


# Flask routes
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/video_feed')
def video_feed():
    return Response(generate_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/attendance')
def get_attendance():
    todays_records = db.get_today_attendance()
    return jsonify(todays_records)

@app.route('/status')
def status():
    now_ts = time.time()
    notice = ''
    if last_notice_ts and (now_ts - last_notice_ts) <= 5:
        notice = last_notice_message

    # Get face names from optimizer for accurate status
    face_names = face_optimizer.known_face_names if face_optimizer.known_face_names else []

    return jsonify({
        'loaded_faces': len(face_names),
        'face_names': face_names,
        'total_attendance': len(db.attendance_data),
        'notice': notice
    })

@app.route('/present')
def present():
    return jsonify(list(db.get_present_today()))

@app.route('/download')
def download():
    lines = []
    header = ['name', 'date', 'punch_in', 'punch_out']
    lines.append(','.join(header))
    for rec in db.attendance_data:
        row = [
            rec.get('name', ''),
            rec.get('date', ''),
            rec.get('punch_in', ''),
            rec.get('punch_out', ''),
        ]
        safe = []
        for v in row:
            v = '' if v is None else str(v)
            if ',' in v:
                safe.append('"' + v.replace('"', '""') + '"')
            else:
                safe.append(v)
        lines.append(','.join(safe))
    content = '\n'.join(lines)
    resp = make_response(content)
    resp.headers['Content-Type'] = 'text/csv'
    resp.headers['Content-Disposition'] = 'attachment; filename=Attendance.csv'
    return resp

@app.route('/clear_attendance', methods=['POST'])
def clear_attendance():
    _ = request.args.get('confirm', 'true')
    result = db.clear_attendance()
    return jsonify(result)


if __name__ == '__main__':
    print("Starting optimized Flask attendance system...")
    app.run(debug=True, host='0.0.0.0', port=5000)