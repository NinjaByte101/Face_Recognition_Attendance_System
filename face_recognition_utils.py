"""
Optimized face recognition utilities module
Contains face recognition related functions with performance optimizations:
- Pre-computed embeddings for instant startup
- FAISS-based approximate nearest neighbor search for fast matching
- Graceful fallbacks to original methods if optimizations unavailable
- Support for both CPU and GPU FAISS indices
- Optimized for 500+ students with fast k-NN search
"""
import cv2
import numpy as np
import os
import pickle
from datetime import datetime
import face_recognition
import threading

# Try to import FAISS for optimized search
try:
    import faiss
    FAISS_AVAILABLE = True
    # Check for GPU support
    try:
        faiss.StandardGpuResources()
        FAISS_GPU_AVAILABLE = True
    except:
        FAISS_GPU_AVAILABLE = False
except ImportError:
    FAISS_AVAILABLE = False
    FAISS_GPU_AVAILABLE = False


class FaceRecognitionOptimizer:
    def __init__(self, images_path='ImagesAttendance', embeddings_path='face_embeddings', use_gpu=False):
        """
        Initialize the face recognition optimizer

        Args:
            images_path (str): Path to directory containing face images
            embeddings_path (str): Path to save/load pre-computed embeddings
            use_gpu (bool): Whether to use GPU acceleration if available
        """
        self.images_path = images_path
        self.embeddings_path = embeddings_path
        self.known_face_embeddings = None
        self.known_face_names = None
        self.faiss_index = None
        self.gpu_index = None
        self.use_gpu = use_gpu and FAISS_GPU_AVAILABLE
        self.embeddings_dim = 128  # face_recognition embedding dimension
        self.index_lock = threading.Lock()  # For thread-safe index operations

        # Create embeddings directory if it doesn't exist
        os.makedirs(os.path.dirname(embeddings_path) if '/' in embeddings_path else '.', exist_ok=True)

        # Try to load pre-computed embeddings
        self.load_embeddings()

        # If no embeddings found, compute from images
        if self.known_face_embeddings is None:
            self.compute_and_save_embeddings()

    def compute_and_save_embeddings(self):
        """Compute face embeddings from images and save them for fast loading"""
        print("Computing face embeddings from images...")

        images = []
        classNames = []
        myList = os.listdir(self.images_path)
        print(f"Loading {len(myList)} images from {self.images_path}...")

        for cls in myList:
            if cls.lower().endswith(('.png', '.jpg', '.jpeg', '.webp')):
                curImg = cv2.imread(f'{self.images_path}/{cls}')
                if curImg is not None:
                    images.append(curImg)
                    classNames.append(os.path.splitext(cls)[0])

        print(f"Successfully loaded {len(classNames)} images: {classNames}")

        # Compute embeddings
        embeddings_list = []
        valid_names = []

        for img, name in zip(images, classNames):
            img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            encodings = face_recognition.face_encodings(img_rgb)

            if encodings:
                embeddings_list.append(encodings[0])
                valid_names.append(name)
            else:
                print(f"Warning: No face found in image {cls}")

        if len(embeddings_list) == 0:
            raise ValueError("No valid face embeddings could be computed from images")

        self.known_face_embeddings = np.array(embeddings_list).astype('float32')
        self.known_face_names = valid_names

        # Save embeddings to disk
        self.save_embeddings()

        # Build FAISS index if available
        if FAISS_AVAILABLE and len(self.known_face_embeddings) > 0:
            self.build_faiss_index()

        print(f"Computed and saved embeddings for {len(self.known_face_names)} faces")

    def save_embeddings(self):
        """Save embeddings and names to disk"""
        if self.known_face_embeddings is not None:
            # Save embeddings as numpy array
            np.save(f'{self.embeddings_path}_embeddings.npy', self.known_face_embeddings)

            # Save names as pickle (or could use JSON/text)
            with open(f'{self.embeddings_path}_names.pkl', 'wb') as f:
                pickle.dump(self.known_face_names, f)

            print(f"Saved embeddings to {self.embeddings_path}_*.npy/.pkl")

    def load_embeddings(self):
        """Load pre-computed embeddings from disk"""
        embeddings_file = f'{self.embeddings_path}_embeddings.npy'
        names_file = f'{self.embeddings_path}_names.pkl'

        if os.path.exists(embeddings_file) and os.path.exists(names_file):
            try:
                self.known_face_embeddings = np.load(embeddings_file).astype('float32')
                with open(names_file, 'rb') as f:
                    self.known_face_names = pickle.load(f)

                print(f"Loaded pre-computed embeddings for {len(self.known_face_names)} faces")

                # Build FAISS index if available
                if FAISS_AVAILABLE and len(self.known_face_embeddings) > 0:
                    self.build_faiss_index()

                return True
            except Exception as e:
                print(f"Error loading embeddings: {e}")
                self.known_face_embeddings = None
                self.known_face_names = None

        return False

    def build_faiss_index(self):
        """Build FAISS index for fast similarity search"""
        if not FAISS_AVAILABLE or self.known_face_embeddings is None:
            return

        with self.index_lock:
            try:
                # Normalize embeddings for cosine similarity (Inner Product with normalized vectors)
                embeddings_copy = self.known_face_embeddings.copy()
                faiss.normalize_L2(embeddings_copy)

                # Choose index type based on dataset size and GPU availability
                n_vectors = len(embeddings_copy)

                if self.use_gpu and FAISS_GPU_AVAILABLE and n_vectors > 100:
                    # Use GPU index for larger datasets
                    res = faiss.StandardGpuResources()
                    # Use IVF-PQ for efficient GPU indexing on larger datasets
                    quantizer = faiss.IndexFlatIP(self.embeddings_dim)
                    nlist = min(int(np.sqrt(n_vectors)) * 2, 256)  # Adaptive number of clusters
                    index_cpu = faiss.IndexIVFPQ(quantizer, self.embeddings_dim, nlist, 16, 8)
                    index_cpu.train(embeddings_copy)
                    index_cpu.add(embeddings_copy)
                    self.gpu_index = faiss.index_cpu_to_gpu(res, 0, index_cpu)
                    self.faiss_index = None  # Keep CPU index as None when using GPU
                    print(f"Built GPU FAISS IVFPQ index with {self.gpu_index.ntotal} vectors (nlist={nlist})")
                elif n_vectors > 1000:
                    # For very large datasets, use IVF index on CPU
                    quantizer = faiss.IndexFlatIP(self.embeddings_dim)
                    nlist = min(int(np.sqrt(n_vectors)), 256)
                    index_cpu = faiss.IndexIVFFlat(quantizer, self.embeddings_dim, nlist, faiss.METRIC_INNER_PRODUCT)
                    index_cpu.train(embeddings_copy)
                    index_cpu.add(embeddings_copy)
                    self.faiss_index = index_cpu
                    self.gpu_index = None
                    print(f"Built CPU FAISS IVFFlat index with {self.faiss_index.ntotal} vectors (nlist={nlist})")
                else:
                    # For smaller datasets, use flat index (exact search)
                    self.faiss_index = faiss.IndexFlatIP(self.embeddings_dim)
                    self.faiss_index.add(embeddings_copy)
                    self.gpu_index = None
                    print(f"Built FAISS flat index with {self.faiss_index.ntotal} vectors")

            except Exception as e:
                print(f"Error building FAISS index: {e}")
                self.faiss_index = None
                self.gpu_index = None

    def find_face_locations_and_encodings(self, frame, scale_factor=0.25):
        """
        Detect face locations and get encodings from a frame

        Args:
            frame: Input frame from webcam
            scale_factor (float): Scale factor for face detection

        Returns:
            tuple: (face_locations, face_encodings)
        """
        # Resize frame for faster processing
        small_frame = cv2.resize(frame, (0, 0), fx=scale_factor, fy=scale_factor)
        rgb_small_frame = cv2.cvtColor(small_frame, cv2.COLOR_BGR2RGB)

        # Find face locations and encodings
        face_locations = face_recognition.face_locations(rgb_small_frame, model='hog')
        face_encodings = face_recognition.face_encodings(rgb_small_frame, face_locations)

        return face_locations, face_encodings

    def recognize_faces_optimized(self, face_encodings, tolerance=0.48, k=1):
        """
        Recognize faces using optimized search (FAISS if available, else linear)
        Returns top-k matches for better semantic search capability

        Args:
            face_encodings: List of face encodings to recognize
            tolerance (float): Tolerance for face matching (lower = stricter)
            k (int): Number of nearest neighbors to return

        Returns:
            list: List of recognized names (empty string for unknown faces)
        """
        if self.known_face_embeddings is None or len(self.known_face_names) == 0:
            return [""] * len(face_encodings)

        recognized_names = []

        for face_encoding in face_encodings:
            name = self._recognize_single_face(face_encoding, tolerance, k)
            recognized_names.append(name)

        return recognized_names

    def _recognize_single_face(self, face_encoding, tolerance=0.48, k=1):
        """Recognize a single face encoding with k-NN search"""
        # Convert to numpy array and normalize for FAISS
        face_encoding_array = np.array([face_encoding]).astype('float32')

        if FAISS_AVAILABLE and ((self.faiss_index is not None) or (self.gpu_index is not None)):
            # Normalize query vector for cosine similarity
            faiss.normalize_L2(face_encoding_array)

            # Search index (GPU or CPU)
            index_to_use = self.gpu_index if self.gpu_index is not None else self.faiss_index
            distances, indices = index_to_use.search(face_encoding_array, k=k)

            # Convert distance to similarity (since we used Inner Product on normalized vectors)
            # distance = 1 - similarity, so similarity = 1 - distance
            similarities = 1 - distances[0]

            # For face_recognition, tolerance is on distance (lower = stricter)
            # We need to convert our similarity back to distance equivalent
            distances_equiv = 1 - similarities

            # Check if the best match is within tolerance
            if distances_equiv[0] <= tolerance:
                match_index = indices[0][0]
                if match_index < len(self.known_face_names):
                    return self.known_face_names[match_index].upper()

        # Fallback to linear search (original method)
        if len(self.known_face_embeddings) > 0:
            face_distances = face_recognition.face_distance(self.known_face_embeddings, face_encoding)
            if len(face_distances) > 0:
                best_match_index = np.argmin(face_distances)
                if face_distances[best_match_index] <= tolerance:
                    return self.known_face_names[best_match_index].upper()

        return ""  # Unknown face

    def recognize_faces_with_confidence(self, face_encodings, tolerance=0.48, k=3):
        """
        Recognize faces and return confidence scores for better semantic understanding

        Returns:
            list of tuples: (name, confidence_score, all_matches)
        """
        if self.known_face_embeddings is None or len(self.known_face_names) == 0:
            return [("", 0.0, [])] * len(face_encodings)

        results = []

        for face_encoding in face_encodings:
            result = self._recognize_single_face_with_confidence(face_encoding, tolerance, k)
            results.append(result)

        return results

    def _recognize_single_face_with_confidence(self, face_encoding, tolerance=0.48, k=3):
        """Recognize a single face with confidence scores"""
        face_encoding_array = np.array([face_encoding]).astype('float32')

        if FAISS_AVAILABLE and ((self.faiss_index is not None) or (self.gpu_index is not None)):
            faiss.normalize_L2(face_encoding_array)
            index_to_use = self.gpu_index if self.gpu_index is not None else self.faiss_index
            distances, indices = index_to_use.search(face_encoding_array, k=k)

            similarities = 1 - distances[0]
            distances_equiv = 1 - similarities

            # Prepare results
            matches = []
            for i in range(min(k, len(indices[0]))):
                idx = indices[0][i]
                if idx < len(self.known_face_names):
                    confidence = max(0.0, 1.0 - distances_equiv[i])  # Convert to 0-1 confidence
                    matches.append((self.known_face_names[idx].upper(), confidence))

            # Return best match if within tolerance
            if matches and distances_equiv[0] <= tolerance:
                best_name, best_confidence = matches[0]
                return (best_name, best_confidence, matches)
            else:
                return ("", 0.0, matches)

        # Fallback to linear search
        if len(self.known_face_embeddings) > 0:
            face_distances = face_recognition.face_distance(self.known_face_embeddings, face_encoding)
            if len(face_distances) > 0:
                best_match_index = np.argmin(face_distances)
                best_distance = face_distances[best_match_index]
                if best_distance <= tolerance:
                    # Calculate confidence based on distance
                    confidence = max(0.0, 1.0 - (best_distance / tolerance)) if tolerance > 0 else 0.0
                    # Get top k matches
                    top_k_indices = np.argsort(face_distances)[:k]
                    matches = []
                    for idx in top_k_indices:
                        if idx < len(self.known_face_names):
                            dist = face_distances[idx]
                            conf = max(0.0, 1.0 - (dist / tolerance)) if tolerance > 0 else 0.0
                            matches.append((self.known_face_names[idx].upper(), conf))
                    return (self.known_face_names[best_match_index].upper(), confidence, matches)

        return ("", 0.0, [])

    def draw_face_boxes(self, frame, face_locations, names, color=(0, 255, 0), thickness=2):
        """
        Draw bounding boxes and labels around detected faces

        Args:
            frame: Input frame to draw on
            face_locations: List of face locations (top, right, bottom, left)
            names: List of names corresponding to each face location
            color: Bounding box color (BGR format)
            thickness: Line thickness for bounding box

        Returns:
            frame: Frame with face boxes drawn
        """
        for (top, right, bottom, left), name in zip(face_locations, names):
            # Scale back up face locations (since we detected in resized frame)
            top *= 4
            right *= 4
            bottom *= 4
            left *= 4

            # Draw bounding box
            cv2.rectangle(frame, (left, top), (right, bottom), color, thickness)

            # Draw label background
            cv2.rectangle(frame, (left, bottom - 35), (right, bottom), color, cv2.FILLED)

            # Draw name text
            font = cv2.FONT_HERSHEY_COMPLEX
            cv2.putText(frame, name, (left + 6, bottom - 6), font, 1.0, (255, 255, 255), 2)

        return frame

    def add_timestamp_to_frame(self, frame, position=(10, 30), font_scale=1.0, color=(255, 255, 0), thickness=2):
        """
        Add current timestamp to frame

        Args:
            frame: Input frame
            position: Position to place timestamp (x, y)
            font_scale: Font size
            color: Text color (BGR format)
            thickness: Line thickness

        Returns:
            frame: Frame with timestamp added
        """
        now = datetime.now()
        date_time_string = now.strftime('%d-%m-%Y %H:%M:%S')
        cv2.putText(frame, date_time_string, position, cv2.FONT_HERSHEY_SIMPLEX, font_scale, color, thickness)
        return frame

    def get_stats(self):
        """Get statistics about the face recognition system"""
        stats = {
            'total_faces': len(self.known_face_names) if self.known_face_names else 0,
            'faiss_available': FAISS_AVAILABLE,
            'faiss_gpu_available': FAISS_GPU_AVAILABLE,
            'using_gpu': self.gpu_index is not None,
            'faiss_index_built': self.faiss_index is not None,
            'gpu_index_built': self.gpu_index is not None,
            'embeddings_loaded': self.known_face_embeddings is not None
        }

        if FAISS_AVAILABLE:
            if self.faiss_index is not None:
                stats['faiss_vectors'] = self.faiss_index.ntotal
                stats['index_type'] = type(self.faiss_index).__name__
            if self.gpu_index is not None:
                stats['gpu_vectors'] = self.gpu_index.ntotal
                stats['gpu_index_type'] = type(self.gpu_index).__name__

        return stats


# Backward compatibility functions (maintain same API as original)
def load_known_faces(images_path='ImagesAttendance'):
    """
    Backward compatibility function - loads known faces
    Uses optimized version if available, otherwise falls back to original
    """
    # This is kept for backward compatibility - the optimizer class is preferred
    optimizer = FaceRecognitionOptimizer(images_path=images_path)
    return optimizer.known_face_embeddings, optimizer.known_face_names


def find_face_locations_and_encodings(frame, scale_factor=0.25):
    """Backward compatibility function"""
    optimizer = FaceRecognitionOptimizer()
    return optimizer.find_face_locations_and_encodings(frame, scale_factor)


def recognize_faces(known_encodings, known_names, face_encodings, tolerance=0.48):
    """Backward compatibility function - now uses optimized search internally"""
    # Create optimizer with the known faces
    optimizer = FaceRecognitionOptimizer()
    optimizer.known_face_embeddings = np.array(known_encodings).astype('float32') if known_encodings else None
    optimizer.known_face_names = known_names

    if FAISS_AVAILABLE and optimizer.known_face_embeddings is not None and len(optimizer.known_face_embeddings) > 0:
        optimizer.build_faiss_index()

    return optimizer.recognize_faces_optimized(face_encodings, tolerance)


def draw_face_boxes(frame, face_locations, names, color=(0, 255, 0), thickness=2):
    """Backward compatibility function"""
    optimizer = FaceRecognitionOptimizer()
    return optimizer.draw_face_boxes(frame, face_locations, names, color, thickness)


def add_timestamp_to_frame(frame, position=(10, 30), font_scale=1.0, color=(255, 255, 0), thickness=2):
    """Backward compatibility function"""
    optimizer = FaceRecognitionOptimizer()
    return optimizer.add_timestamp_to_frame(frame, position, font_scale, color, thickness)