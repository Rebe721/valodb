# ベースイメージとしてPython 3.9を使用
FROM python:3.9-slim

# 作業ディレクトリを設定
WORKDIR /app

# 必要なファイルをコンテナ内にコピー
COPY . /app

# 必要なパッケージをインストール
RUN pip install --no-cache-dir -r requirements.txt

# 環境変数を設定（Discord Botのトークンを使う）
# Docker Composeを使用する場合は、docker-compose.ymlにTOKENを指定する方がよいです
# ENV TOKEN=your_discord_bot_token

# ポート8080を公開（keep_aliveサーバー用）
EXPOSE 8080

# Botの起動コマンド
CMD ["python", "main.py"]
