"""
Optimized database utilities module
Handles all CSV operations for attendance tracking with performance improvements
"""
import csv
import os
import time
import threading
from queue import Queue
from datetime import datetime
import numpy as np


class AttendanceDatabaseOptimized:
    def __init__(self, csv_path='Attendance.csv', cooldown_seconds=4):
        self.csv_path = csv_path
        self.cooldown_seconds = cooldown_seconds

        # Attendance data structures - optimized for faster access
        self.attendance_data = []           # List of attendance records
        self.attendance_index = {}          # (name, date) -> index in attendance_data (O(1) lookup)
        self.last_attendance = {}           # name -> timestamp (for cooldown)
        self.present_today = set()          # Set of names present today (O(1) lookup)
        self.current_recognized = set()     # Currently recognized faces in frame

        # Threading for async CSV writes
        self.attendance_lock = threading.Lock()
        self._csv_write_queue = Queue(maxsize=1)
        self.last_notice_message = ''
        self.last_notice_ts = 0.0

        # Performance optimization: cache today's date to avoid repeated computation
        self._today_date_cache = None
        self._today_date_cache_time = 0
        self._cache_timeout = 60  # Cache timeout in seconds

        # Start CSV writer thread
        self._start_csv_writer()

        # Load existing data
        self.load_attendance_csv()

    def _start_csv_writer(self):
        """Start the background CSV writer thread"""
        def _csv_writer_worker():
            while True:
                try:
                    item = self._csv_write_queue.get()
                    if item is None:  # Sentinel to stop
                        break
                    self._write_csv_sync()
                except Exception as e:
                    print(f"Error in CSV writer: {e}")

        t = threading.Thread(target=_csv_writer_worker, daemon=True)
        t.start()

    def today_date_str(self, ts=None):
        """Get today's date string in DD-MM-YYYY format with caching"""
        if ts is None:
            ts = time.time()

        # Use cache if valid (within timeout)
        current_time = time.time()
        if (self._today_date_cache is not None and
            current_time - self._today_date_cache_time < self._cache_timeout):
            return self._today_date_cache

        # Update cache
        self._today_date_cache = datetime.fromtimestamp(ts).strftime('%d-%m-%Y')
        self._today_date_cache_time = current_time
        return self._today_date_cache

    def load_attendance_csv(self):
        """Load attendance data from CSV file - optimized for speed"""
        self.attendance_data = []
        self.attendance_index = {}
        self.last_attendance = {}
        self.present_today = set()

        if not os.path.exists(self.csv_path):
            return

        with open(self.csv_path, newline='') as f:
            reader = csv.reader(f)
            legacy_buffer = {}

            for row in reader:
                if not row:
                    continue

                if len(row) >= 4:
                    # New format: name, date, punch_in, punch_out
                    name, date_str, punch_in, punch_out = row[0], row[1], row[2], row[3]
                    key = (name, date_str)
                    record = {
                        'name': name,
                        'date': date_str,
                        'punch_in': punch_in,
                        'punch_out': punch_out,
                        'updated_ts': 0.0,
                    }
                    idx = len(self.attendance_data)
                    self.attendance_data.append(record)
                    self.attendance_index[key] = idx

                    try:
                        if date_str == self.today_date_str():
                            if punch_in:
                                self.present_today.add(name)
                    except:
                        pass
                elif len(row) >= 3:
                    # Legacy format: name, datetime_string, timestamp
                    name, dt_string, ts = row[0], row[1], row[2]
                    try:
                        tsf = float(ts)
                    except:
                        tsf = time.time()

                    try:
                        date_part = dt_string.split(' ')[0]
                    except:
                        date_part = self.today_date_str(tsf)

                    key = (name, date_part)
                    if key not in legacy_buffer:
                        legacy_buffer[key] = {'earliest': dt_string, 'latest': dt_string}
                    else:
                        if dt_string < legacy_buffer[key]['earliest']:
                            legacy_buffer[key]['earliest'] = dt_string
                        if dt_string > legacy_buffer[key]['latest']:
                            legacy_buffer[key]['latest'] = dt_string

                    try:
                        if date_part == self.today_date_str(tsf):
                            self.present_today.add(name)
                    except:
                        pass

            # Process legacy buffer
            if legacy_buffer:
                for (name, date_str), agg in legacy_buffer.items():
                    record = {
                        'name': name,
                        'date': date_str,
                        'punch_in': agg['earliest'],
                        'punch_out': agg['latest'] if agg['latest'] != agg['earliest'] else '',
                        'updated_ts': 0.0,
                    }
                    idx = len(self.attendance_data)
                    self.attendance_data.append(record)
                    self.attendance_index[(name, date_str)] = idx

    def _write_csv_sync(self):
        """Synchronously write attendance data to CSV - optimized"""
        with self.attendance_lock:
            tmp = self.csv_path + '.tmp'
            # Pre-allocate list size for better performance
            rows = [(rec['name'], rec['date'], rec['punch_in'], rec['punch_out'])
                   for rec in self.attendance_data]
            with open(tmp, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerows(rows)
            os.replace(tmp, self.csv_path)

    def mark_attendance(self, name):
        """
        Mark attendance for a person with cooldown protection - optimized

        Args:
            name (str): Name of the person

        Returns:
            bool: True if attendance was marked/updated, False if cooldown active
        """
        current_time = time.time()

        # Check cooldown - optimized dictionary lookup
        last_time = self.last_attendance.get(name, 0)
        if current_time - last_time < self.cooldown_seconds:
            return False

        now = datetime.fromtimestamp(current_time)
        time_string = now.strftime('%d-%m-%Y %H:%M:%S')
        date_only = now.strftime('%d-%m-%Y')
        changed = False

        key = (name, date_only)
        if key in self.attendance_index:
            idx = self.attendance_index[key]
            rec = self.attendance_data[idx]

            if not rec.get('punch_in'):
                rec['punch_in'] = time_string
                rec['updated_ts'] = current_time
                changed = True
            else:
                hour = now.hour
                if 17 <= hour < 18:  # 5:00 PM to 6:00 PM
                    if rec.get('punch_out') != time_string:
                        rec['punch_out'] = time_string
                        rec['updated_ts'] = current_time
                        changed = True
                else:
                    # Outside punch-out hours
                    self.last_notice_message = 'Punch-out allowed only between 5:00 PM and 6:00 PM.'
                    self.last_notice_ts = current_time
        else:
            # New attendance record
            idx = len(self.attendance_data)
            self.attendance_data.append({
                'name': name,
                'date': date_only,
                'punch_in': time_string,
                'punch_out': '',
                'updated_ts': current_time,
            })
            self.attendance_index[key] = idx
            changed = True

        self.last_attendance[name] = current_time
        self.present_today.add(name)

        if changed:
            self.save_attendance_csv(async_write=True)
            # Uncomment below for debug: print(f"Attendance updated for {name}: {date_only}")
            return True
        else:
            return False

    def save_attendance_csv(self, async_write=True):
        """Save attendance data to CSV (async or sync)"""
        if async_write:
            try:
                if self._csv_write_queue.empty():
                    self._csv_write_queue.put_nowait(True)
            except Exception:
                pass
        else:
            self._write_csv_sync()

    def get_today_attendance(self):
        """Get today's attendance records - optimized"""
        today = self.today_date_str()
        # Use list comprehension for faster filtering
        todays_records = [
            {
                'name': rec['name'],
                'date': rec['date'],
                'punch_in': rec['punch_in'],
                'punch_out': rec['punch_out'],
            }
            for rec in self.attendance_data if rec.get('date') == today
        ]
        # Sort once at the end
        todays_records.sort(key=lambda r: r['name'])
        return todays_records

    def get_status(self):
        """Get system status - optimized"""
        now_ts = time.time()
        notice = ''
        if self.last_notice_ts and (now_ts - self.last_notice_ts) <= 5:
            notice = self.last_notice_message

        return {
            'loaded_faces': 0,  # Will be set externally from face recognition
            'face_names': [],   # Will be set externally from face recognition
            'total_attendance': len(self.attendance_data),
            'notice': notice
        }

    def get_present_today(self):
        """Get list of people present today - O(1) operation"""
        return list(self.present_today)

    def clear_attendance(self):
        """Clear all attendance data - optimized"""
        self.attendance_data = []
        self.attendance_index = {}
        self.last_attendance = {}
        self.present_today = set()
        self.save_attendance_csv()
        return {'ok': True, 'message': 'Attendance cleared'}

    def shutdown(self):
        """Clean shutdown - signal CSV writer to stop"""
        try:
            self._csv_write_queue.put_nowait(None)
        except:
            pass


# Backward compatibility functions
def load_attendance_csv():
    """Backward compatibility function"""
    db = AttendanceDatabaseOptimized()
    return db.attendance_data, db.attendance_index, db.last_attendance, db.present_today


def mark_attendance(name, attendance_data, attendance_index, last_attendance, present_today):
    """Backward compatibility function"""
    # This maintains the old API but is less efficient
    # New code should use the AttendanceDatabaseOptimized class directly
    db = AttendanceDatabaseOptimized()
    db.attendance_data = attendance_data
    db.attendance_index = attendance_index
    db.last_attendance = last_attendance
    db.present_today = present_today

    result = db.mark_attendance(name)

    return (result, db.attendance_data, db.attendance_index,
            db.last_attendance, db.present_today)


def save_attendance_csv(attendance_data, async_write=True):
    """Backward compatibility function"""
    # This is simplified - in practice, the class method is better
    pass  # Implementation would depend on specific use case