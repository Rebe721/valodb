import os
import json
import logging
from flask import Flask
from threading import Thread
import discord
from discord.ext import commands
from discord.ui import View, Select
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

# Flaskアプリのセットアップ（Koyebのヘルスチェック用）
app = Flask(__name__)

@app.route('/')
def home():
    return "Instance is healthy. All health checks are passing."

def run():
    app.run(host="0.0.0.0", port=8080)

# 環境変数からTOKENとCREDENTIALS_JSONを取得
DISCORD_TOKEN = os.getenv("TOKEN")
CREDENTIALS_JSON = os.getenv("CREDENTIALS_JSON")

if not DISCORD_TOKEN or not CREDENTIALS_JSON:
    raise EnvironmentError("環境変数 'TOKEN' または 'CREDENTIALS_JSON' が設定されていません。")

# Google Sheets APIの認証
credentials = Credentials.from_service_account_info(json.loads(CREDENTIALS_JSON))
sheets_service = build("sheets", "v4", credentials=credentials)
SPREADSHEET_ID = "1_xEKOwz4WsYv7C4bQRpwuRl4AOJnokFZktVpB9yIRCc"  # 必要に応じて設定してください

# Discord Botのセットアップ
intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

logging.basicConfig(level=logging.INFO)

# Google Sheetsからデータ取得
def get_sheet_data(range_name):
    sheet = sheets_service.spreadsheets()
    result = sheet.values().get(spreadsheetId=SPREADSHEET_ID, range=range_name).execute()
    return result.get("values", [])

# Google Sheetsにデータ書き込み
def update_sheet_data(range_name, values):
    body = {"values": values}
    sheet = sheets_service.spreadsheets()
    result = sheet.values().update(
        spreadsheetId=SPREADSHEET_ID, range=range_name,
        valueInputOption="RAW", body=body
    ).execute()
    return result

class AccountSelectView(View):
    def __init__(self, user_id: str, records: list):
        super().__init__(timeout=900.0)  # タイムアウトを15分に設定
        self.user_id = user_id
        self.records = records

        # プルダウンメニューのオプションを生成
        self.account_selection = Select(
            placeholder="利用するアカウントを選んでください",
            min_values=1,
            max_values=1,
            options=[
                discord.SelectOption(label=record["name"], value=str(index))
                for index, record in enumerate(records)
            ]
        )
        self.account_selection.callback = self.on_select_account
        self.add_item(self.account_selection)

    async def on_select_account(self, interaction: discord.Interaction):
        try:
            # 選択されたアカウントのインデックスを取得
            selected_index = int(self.account_selection.values[0])
            selected_account = self.records[selected_index]

            # すでに借りているアカウントがあるか確認
            current_borrowed = next(
                (record for record in self.records if record.get("borrower") == self.user_id),
                None
            )
            if current_borrowed:
                await interaction.response.send_message(
                    f"あなたは既にアカウント **{current_borrowed['name']}** を借りています。返却してください。",
                    ephemeral=True
                )
                return

            # スプレッドシートの更新
            selected_account["status"] = "borrowed"
            selected_account["borrower"] = self.user_id
            update_sheet_data("Accounts!A2:F", self.records)  # 必要に応じてシート範囲を変更

            # 応答メッセージを送信
            await interaction.response.send_message(
                f"アカウント **{selected_account['name']}** の詳細:\n"
                f"**ID**: {selected_account['id']}\n"
                f"**パスワード**: {selected_account['password']}\n"
                f"**ランク**: {selected_account['rank']}",
                ephemeral=True
            )

            # 全体通知
            channel = bot.get_channel(1307661467578925056)  # 通知用チャンネルID
            if channel is not None:
                await channel.send(f"ユーザー <@{self.user_id}> がアカウント **{selected_account['name']}** を借りました！")
        except Exception as e:
            logging.error(f"選択処理中のエラー: {e}")
            await interaction.response.send_message("アカウント選択中にエラーが発生しました。", ephemeral=True)

# アカウント利用
@bot.tree.command(name="use_account")
async def use_account(interaction: discord.Interaction):
    user_id = str(interaction.user.id)
    records = [
        {"name": row[0], "id": row[1], "password": row[2], "rank": row[3], "status": row[4], "borrower": row[5]}
        for row in get_sheet_data("Sheet1!A2:F")
    ]

    # ユーザーがすでに借りているアカウントを確認
    borrowed_account = next((record for record in records if record.get("borrower") == user_id), None)
    if borrowed_account:
        await interaction.response.send_message(
            f"あなたは既にアカウント **{borrowed_account['name']}** を借りています。返却してください。",
            ephemeral=True
        )
        return

    # 利用可能なアカウントを取得
    available_accounts = [record for record in records if record.get("status") == "available"]
    if not available_accounts:
        await interaction.response.send_message("利用可能なアカウントがありません。", ephemeral=True)
        return

    # アカウント選択メニューを表示
    await interaction.response.send_message(
        "利用するアカウントを選んでください:",
        view=AccountSelectView(user_id, available_accounts),
        ephemeral=True
    )

# FlaskアプリとDiscordボットを同時実行
def keep_alive():
    t = Thread(target=run)
    t.start()

if __name__ == "__main__":
    keep_alive()
    bot.run(DISCORD_TOKEN)
