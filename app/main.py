import os
import json
import logging
from flask import Flask
from threading import Thread
import discord
from discord.ext import commands
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

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")

@bot.tree.command(name="return_account")
async def return_account(interaction: discord.Interaction, name: str):
    user_id = str(interaction.user.id)
    try:
        records = get_sheet_data("Accounts!A2:F")  # 必要に応じてシート名を変更してください
        for index, record in enumerate(records):
            if len(record) >= 6:  # borrowerカラムが存在することを確認
                account_name = record[0].strip() if record[0] else ""
                borrower = str(record[5]).strip() if len(record) > 5 else ""

                if account_name == name and borrower == user_id:
                    # アカウントのステータスを更新
                    records[index][4] = "available"  # 状態を "available" に
                    records[index][5] = ""  # borrowerをクリア
                    update_sheet_data(f"Sheet1!A2:F{len(records)+1}", records)

                    await interaction.response.send_message(
                        f"アカウント **{name}** を返却しました！", ephemeral=True
                    )
                    return
        await interaction.response.send_message(
            "指定されたアカウントが見つかりませんでした。", ephemeral=True
        )
    except Exception as e:
        logging.error(f"return_accountエラー: {e}")
        await interaction.response.send_message("エラーが発生しました。", ephemeral=True)

class AccountSelectView(discord.ui.View):
    def __init__(self, user_id, records):
        super().__init__(timeout=900.0)
        self.user_id = user_id
        self.records = records
        self.account_selection = discord.ui.Select(
            placeholder="利用するアカウントを選んでください",
            options=[
                discord.SelectOption(label=record[0], value=str(index))
                for index, record in enumerate(records)
            ]
        )
        self.account_selection.callback = self.on_select_account
        self.add_item(self.account_selection)

    async def on_select_account(self, interaction: discord.Interaction):
        try:
            selected_index = int(self.account_selection.values[0])
            selected_account = self.records[selected_index]

            # Google Sheets更新
            self.records[selected_index][4] = "borrowed"
            self.records[selected_index][5] = self.user_id
            update_sheet_data(f"Sheet1!A2:F{len(self.records)+1}", self.records)

            # 応答メッセージ送信
            await interaction.response.send_message(
                f"アカウント **{selected_account[0]}** の詳細:\n"
                f"**ID**: {selected_account[1]}\n"
                f"**パスワード**: {selected_account[2]}\n"
                f"**ランク**: {selected_account[3]}",
                ephemeral=True
            )

            # 通知チャンネルへの送信
            try:
                channel = bot.get_channel(1307661467578925056)  # チャンネルIDを適切に設定
                if channel:
                    await channel.send(
                        f"ユーザー <@{self.user_id}> がアカウント **{selected_account[0]}** を借りました！"
                    )
                else:
                    logging.warning("通知チャンネルが見つかりませんでした。")
            except discord.errors.Forbidden:
                logging.warning("通知チャンネルへのアクセス権がありません。")
        except Exception as e:
            logging.error(f"アカウント選択処理中のエラー: {e}")
            try:
                await interaction.response.send_message(
                    "アカウント選択中にエラーが発生しました。", ephemeral=True
                )
            except discord.errors.InteractionResponded:
                logging.warning("インタラクションはすでに応答済みです。")

def keep_alive():
    t = Thread(target=run)
    t.start()

if __name__ == "__main__":
    keep_alive()
    bot.run(TOKEN)
