# ... (начало файла не трогаем)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем вообще всё содержимое репозитория разом:
COPY . .

# Дальше идут команды запуска (CMD или ENTRYPOINT), их оставляем как было
