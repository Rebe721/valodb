import discord
from discord.ext import commands
from googleapiclient.discovery import build
from google.oauth2.service_account import Credentials
import json
import os
import threading
from flask import Flask
import gspread

# Flask アプリ作成
app = Flask(__name__)

@app.route("/")
def health_check():
    return "OK", 200

# Flask サーバー起動
def run_server():
    app.run(host="0.0.0.0", port=8080)

server_thread = threading.Thread(target=run_server)
server_thread.daemon = True
server_thread.start()

# Google Sheets API 設定
SCOPES = ['https://www.googleapis.com/auth/spreadsheets']
credentials_info = json.loads(os.environ["CREDENTIALS_JSON"])  # 環境変数から認証情報を取得
credentials = Credentials.from_service_account_info(credentials_info, scopes=SCOPES)
service = build('sheets', 'v4', credentials=credentials)
gc = gspread.authorize(credentials)

SPREADSHEET_ID = "1_xEKOwz4WsYv7C4bQRpwuRl4AOJnokFZktVpB9yIRCc"
sheet = gc.open_by_key(SPREADSHEET_ID).sheet1

# Discord Bot 設定
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# アカウント操作関数
def get_available_accounts():
    records = sheet.get_all_records()
    return [record for record in records if record["Status"] == "available"]

def update_account_status(name, status, borrower=None, rank=None):
    records = sheet.get_all_records()
    for i, record in enumerate(records):
        if record["Name"] == name:
            sheet.update_cell(i + 2, 5, status)  # Status列
            sheet.update_cell(i + 2, 6, borrower or "")  # Borrower列
            if rank:
                sheet.update_cell(i + 2, 4, rank)  # Rank列
            break

# プルダウンメニューを含むView
class AccountSelectView(discord.ui.View):
    def __init__(self, user_id):
        super().__init__(timeout=None)

        available_accounts = get_available_accounts()

        options = [
            discord.SelectOption(label=f"{account['Name']} - {account['Rank']}", value=account['Name'])
            for account in available_accounts
        ]

        self.select_menu = discord.ui.Select(
            placeholder="利用するアカウントを選んでください",
            options=options
        )
        self.select_menu.callback = self.on_select_account
        self.add_item(self.select_menu)

    async def on_select_account(self, interaction: discord.Interaction):
        selected_account = self.select_menu.values[0]
        update_account_status(selected_account, "borrowed", interaction.user.id)
        await interaction.response.send_message(
            f"アカウント **{selected_account}** を借りました！",
            ephemeral=True
        )

# スラッシュコマンド: アカウント利用
@bot.tree.command(name="use_account")
async def use_account(interaction: discord.Interaction):
    user_id = str(interaction.user.id)
    available_accounts = get_available_accounts()
    if not available_accounts:
        await interaction.response.send_message("利用可能なアカウントがありません。", ephemeral=True)
    else:
        await interaction.response.send_message("利用するアカウントを選んでください:", view=AccountSelectView(user_id), ephemeral=True)

# Bot起動
bot.run(os.environ["TOKEN"])
