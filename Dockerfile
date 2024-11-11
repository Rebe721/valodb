FROM python:3.11

# 作業ディレクトリを指定
WORKDIR /bot

# 日本語環境の設定
RUN apt-get update && apt-get -y install locales && apt-get -y upgrade && \
    localedef -f UTF-8 -i ja_JP ja_JP.UTF-8
ENV LANG ja_JP.UTF-8
ENV LANGUAGE ja_JP:ja
ENV LC_ALL ja_JP.UTF-8
ENV TZ Asia/Tokyo
ENV TERM xterm

# requirements.txtをコピーし、依存関係をインストール
COPY requirements.txt /bot/
RUN pip install -r requirements.txt

# アプリケーションファイルをコピー
COPY . /bot

# 必要なポートを開放 (keep_alive.pyなどが利用するポート)
EXPOSE 8080

# コンテナ起動時に実行するコマンド
CMD python app/main.py
