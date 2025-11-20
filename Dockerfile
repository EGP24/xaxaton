# Используем Python 3.11 с поддержкой системных библиотек
FROM python:3.11-slim

# Устанавливаем системные зависимости для face-recognition и opencv
RUN apt-get update && apt-get install -y \
    build-essential \
    cmake \
    libopenblas-dev \
    liblapack-dev \
    libx11-dev \
    libgtk-3-dev \
    libboost-all-dev \
    git \
    wget \
    && rm -rf /var/lib/apt/lists/*

# Устанавливаем dlib (требуется для face-recognition)
RUN pip install --no-cache-dir dlib

# Создаем рабочую директорию
WORKDIR /app

# Копируем requirements.txt
COPY requirements.txt .

# Устанавливаем Python зависимости
RUN pip install --no-cache-dir -r requirements.txt

# Копируем все файлы приложения
COPY . .

# Создаем директорию для базы данных если её нет
RUN mkdir -p /app/data

# Открываем порт
EXPOSE 8888

# Команда запуска
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8888", "--reload"]

