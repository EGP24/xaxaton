import dlib
import numpy as np
from PIL import Image
import io
import json
from typing import List, Dict, Tuple, Optional
from sqlalchemy.orm import Session
from models import Student
import cv2


class FaceRecognitionService:

    def __init__(self, tolerance: float = 0.6):
        self.tolerance = tolerance
        self.detector = dlib.get_frontal_face_detector()
        self.shape_predictor = None
        self.face_encoder = None

    def _ensure_models(self):
        if self.shape_predictor is None:
            try:
                self.shape_predictor = dlib.shape_predictor('shape_predictor_68_face_landmarks.dat')
                self.face_encoder = dlib.face_recognition_model_v1('dlib_face_recognition_resnet_model_v1.dat')
            except:
                print("⚠️ Модели dlib не найдены. Система будет работать в упрощенном режиме.")
                print("Для полной функциональности скачайте модели:")
                print("http://dlib.net/files/shape_predictor_68_face_landmarks.dat.bz2")
                print("http://dlib.net/files/dlib_face_recognition_resnet_model_v1.dat.bz2")
                self.shape_predictor = "simple"
                self.face_encoder = "simple"

    def extract_face_encoding(self, image_bytes: bytes) -> Optional[List[float]]:
        try:
            self._ensure_models()

            image = Image.open(io.BytesIO(image_bytes))
            if image.mode != 'RGB':
                image = image.convert('RGB')

            img_array = np.array(image)

            faces = self.detector(img_array, 1)

            if len(faces) == 0:
                return None

            face = faces[0]

            if self.shape_predictor == "simple":
                encoding = [
                    float(face.left()), float(face.top()),
                    float(face.right()), float(face.bottom()),
                    float(face.width()), float(face.height())
                ]
                encoding.extend([0.0] * 122)
            else:
                shape = self.shape_predictor(img_array, face)
                face_descriptor = self.face_encoder.compute_face_descriptor(img_array, shape)
                encoding = list(face_descriptor)

            return encoding

        except Exception as e:
            print(f"Ошибка при извлечении лица: {e}")
            import traceback
            traceback.print_exc()
            return None

    def extract_all_faces(self, image_bytes: bytes) -> List[List[float]]:
        try:
            self._ensure_models()

            image = Image.open(io.BytesIO(image_bytes))
            if image.mode != 'RGB':
                image = image.convert('RGB')

            img_array = np.array(image)

            faces = self.detector(img_array, 1)

            encodings = []
            for face in faces:
                if self.shape_predictor == "simple":
                    encoding = [
                        float(face.left()), float(face.top()),
                        float(face.right()), float(face.bottom()),
                        float(face.width()), float(face.height())
                    ]
                    encoding.extend([0.0] * 122)
                else:
                    shape = self.shape_predictor(img_array, face)
                    face_descriptor = self.face_encoder.compute_face_descriptor(img_array, shape)
                    encoding = list(face_descriptor)
                encodings.append(encoding)

            return encodings
        except Exception as e:
            print(f"Ошибка при извлечении лиц: {e}")
            import traceback
            traceback.print_exc()
            return []

    def save_student_face(self, student_id: int, image_bytes: bytes, db: Session) -> bool:
        encoding = self.extract_face_encoding(image_bytes)
        if encoding is None:
            return False

        student = db.query(Student).filter(Student.id == student_id).first()
        if not student:
            return False

        student.face_encoding = json.dumps(encoding)
        db.commit()
        return True

    def recognize_students(
        self,
        image_bytes: bytes,
        students: List[Student]
    ) -> Tuple[List[int], int]:
        self._ensure_models()

        photo_encodings = self.extract_all_faces(image_bytes)

        if not photo_encodings:
            return [], 0

        recognized_ids = []

        student_encodings = {}
        for student in students:
            if student.face_encoding:
                try:
                    encoding = np.array(json.loads(student.face_encoding))
                    student_encodings[student.id] = encoding
                except:
                    continue

        for photo_encoding in photo_encodings:
            photo_enc_array = np.array(photo_encoding)

            best_match_id = None
            best_distance = float('inf')

            for student_id, student_encoding in student_encodings.items():
                distance = np.linalg.norm(student_encoding - photo_enc_array)

                if distance < best_distance and distance <= self.tolerance:
                    best_distance = distance
                    best_match_id = student_id

            if best_match_id is not None and best_match_id not in recognized_ids:
                recognized_ids.append(best_match_id)

        return recognized_ids, len(photo_encodings)

    def get_recognition_stats(
        self,
        recognized_ids: List[int],
        total_faces: int,
        total_students: int
    ) -> Dict[str, any]:
        return {
            "recognized_count": len(recognized_ids),
            "total_faces": total_faces,
            "total_students": total_students,
            "recognition_rate": len(recognized_ids) / total_students if total_students > 0 else 0,
            "unrecognized_faces": max(0, total_faces - len(recognized_ids))
        }

