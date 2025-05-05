FROM python:3.9-slim

WORKDIR /app

# gitをインストール（←ここが重要！）
RUN apt-get update && apt-get install -y git

# requirements.txt を先にコピーして依存だけインストール（キャッシュ効かせる）
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# アプリの中身を全部コピー
COPY . .

# Fly.io用：Gunicornでapp.py内のFlaskアプリ(app)を起動
CMD ["gunicorn", "app:app", "--bind", "0.0.0.0:5000"]
