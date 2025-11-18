"""Сервис распознавания лиц студентов с использованием dlib"""
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
    """Сервис для распознавания лиц на фотографиях"""

    def __init__(self, tolerance: float = 0.6):
        """
        Args:
            tolerance: Порог для сравнения лиц (меньше = строже, по умолчанию 0.6)
        """
        self.tolerance = tolerance
        self.detector = dlib.get_frontal_face_detector()
        self.shape_predictor = None
        self.face_encoder = None

    def _ensure_models(self):
        """Ленивая загрузка моделей dlib"""
        if self.shape_predictor is None:
            try:
                # Пытаемся загрузить предобученные модели
                self.shape_predictor = dlib.shape_predictor('shape_predictor_68_face_landmarks.dat')
                self.face_encoder = dlib.face_recognition_model_v1('dlib_face_recognition_resnet_model_v1.dat')
            except:
                # Если моделей нет, используем упрощенный подход
                print("⚠️ Модели dlib не найдены. Система будет работать в упрощенном режиме.")
                print("Для полной функциональности скачайте модели:")
                print("http://dlib.net/files/shape_predictor_68_face_landmarks.dat.bz2")
                print("http://dlib.net/files/dlib_face_recognition_resnet_model_v1.dat.bz2")
                self.shape_predictor = "simple"
                self.face_encoder = "simple"

    def extract_face_encoding(self, image_bytes: bytes) -> Optional[List[float]]:
        """
        Извлекает эмбеддинг лица из изображения

        Args:
            image_bytes: Байты изображения

        Returns:
            Список с эмбеддингом лица или None, если лицо не найдено
        """
        try:
            self._ensure_models()

            # Загружаем изображение
            image = Image.open(io.BytesIO(image_bytes))
            # Конвертируем в RGB если нужно
            if image.mode != 'RGB':
                image = image.convert('RGB')

            # Конвертируем в numpy array
            img_array = np.array(image)

            # Находим лица
            faces = self.detector(img_array, 1)

            if len(faces) == 0:
                return None

            # Используем первое найденное лицо
            face = faces[0]

            if self.shape_predictor == "simple":
                # Упрощенный режим - используем координаты bounding box как "эмбеддинг"
                encoding = [
                    float(face.left()), float(face.top()),
                    float(face.right()), float(face.bottom()),
                    float(face.width()), float(face.height())
                ]
                # Добавляем случайные признаки для совместимости
                encoding.extend([0.0] * 122)  # Всего 128 чисел
            else:
                # Полный режим с предобученными моделями
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
        """
        Извлекает все лица с фотографии

        Args:
            image_bytes: Байты изображения

        Returns:
            Список эмбеддингов всех найденных лиц
        """
        try:
            self._ensure_models()

            # Загружаем изображение
            image = Image.open(io.BytesIO(image_bytes))
            if image.mode != 'RGB':
                image = image.convert('RGB')

            img_array = np.array(image)

            # Находим все лица
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
        """
        Сохраняет эмбеддинг лица студента в базу данных

        Args:
            student_id: ID студента
            image_bytes: Байты изобра��ения с лицом студента
            db: Сессия базы данных

        Returns:
            True если успешно, False иначе
        """
        encoding = self.extract_face_encoding(image_bytes)
        if encoding is None:
            return False

        student = db.query(Student).filter(Student.id == student_id).first()
        if not student:
            return False

        # Сохраняем эмбеддинг как JSON
        student.face_encoding = json.dumps(encoding)
        db.commit()
        return True

    def recognize_students(
        self,
        image_bytes: bytes,
        students: List[Student]
    ) -> Tuple[List[int], int]:
        """
        Распознает студентов на групповом фото

        Args:
            image_bytes: Байты изображения с группой студентов
            students: Список студентов для сравнения

        Returns:
            Кортеж (список ID распознанных студентов, общее количество лиц на фото)
        """
        self._ensure_models()

        # Извлекаем все лица с фото
        photo_encodings = self.extract_all_faces(image_bytes)

        if not photo_encodings:
            return [], 0

        recognized_ids = []

        # Получаем эмбеддинги студентов из базы
        student_encodings = {}
        for student in students:
            if student.face_encoding:
                try:
                    encoding = np.array(json.loads(student.face_encoding))
                    student_encodings[student.id] = encoding
                except:
                    continue

        # Сравниваем каждое лицо с фото с эмбеддингами студентов
        for photo_encoding in photo_encodings:
            photo_enc_array = np.array(photo_encoding)

            best_match_id = None
            best_distance = float('inf')

            for student_id, student_encoding in student_encodings.items():
                # Вычисляем евклидово расстояние между эмбеддингами
                distance = np.linalg.norm(student_encoding - photo_enc_array)

                # Если это лучшее совпадение и оно в пределах порога
                if distance < best_distance and distance <= self.tolerance:
                    best_distance = distance
                    best_match_id = student_id

            # Если нашли совпадение и студент еще не распознан
            if best_match_id is not None and best_match_id not in recognized_ids:
                recognized_ids.append(best_match_id)

        return recognized_ids, len(photo_encodings)

    def get_recognition_stats(
        self,
        recognized_ids: List[int],
        total_faces: int,
        total_students: int
    ) -> Dict[str, any]:
        """
        Возвращает статистику распознавания

        Args:
            recognized_ids: Список ID распознанных студентов
            total_faces: Общее количество лиц на фото
            total_students: Общее количество студентов в группе

        Returns:
            Словарь со статистикой
        """
        return {
            "recognized_count": len(recognized_ids),
            "total_faces": total_faces,
            "total_students": total_students,
            "recognition_rate": len(recognized_ids) / total_students if total_students > 0 else 0,
            "unrecognized_faces": max(0, total_faces - len(recognized_ids))
        }

