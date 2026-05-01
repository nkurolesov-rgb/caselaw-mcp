FROM python:3.13-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Сначала копируем только зависимости и устанавливаем их
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Вот та самая универсальная команда: копируем вообще ВСЕ оставшиеся файлы проекта разом
COPY . .

# Команда для запуска сервера (скорее всего, она выглядит так)
CMD ["python", "server.py"]
