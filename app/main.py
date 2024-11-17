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

# アカウントの操作関数
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

def can_borrow_account(user_id):
    records = sheet.get_all_records()
    return all(record["Borrower"] != str(user_id) for record in records)

# Botイベント
@bot.event
async def on_ready():
    print(f'Logged in as {bot.user}')

# スラッシュコマンド
@bot.tree.command(name="use_account")
async def use_account(interaction: discord.Interaction):
    user_id = str(interaction.user.id)
    if not can_borrow_account(user_id):
        await interaction.response.send_message("既にアカウントを借りています。返却してください。", ephemeral=True)
        return

    available_accounts = get_available_accounts()
    if not available_accounts:
        await interaction.response.send_message("利用可能なアカウントがありません。", ephemeral=True)
        return

    options = [
        discord.SelectOption(label=f"{record['Name']} - {record['Rank']}", value=record["Name"])
        for record in available_accounts
    ]

    class AccountSelectView(discord.ui.View):
        @discord.ui.select(placeholder="利用するアカウントを選んでください", options=options)
        async def select_callback(self, select: discord.ui.Select, interaction: discord.Interaction):
            selected_account = self.children[0].values[0]
            update_account_status(selected_account, "borrowed", interaction.user.id)
            await interaction.response.send_message(
                f"アカウント **{selected_account}** を借りました！", ephemeral=True
            )
            await interaction.channel.send(f"**{interaction.user.name}** がアカウント **{selected_account}** を借りました！")

    await interaction.response.send_message("利用するアカウントを選んでください:", view=AccountSelectView(), ephemeral=True)

@bot.tree.command(name="return_account")
async def return_account(interaction: discord.Interaction, name: str, new_rank: str):
    user_id = str(interaction.user.id)
    records = sheet.get_all_records()
    for record in records:
        if record["Name"] == name and record["Borrower"] == user_id:
            update_account_status(name, "available", rank=new_rank)
            await interaction.response.send_message(f"アカウント **{name}** を返却しました。ランクを更新しました。", ephemeral=True)
            return
    await interaction.response.send_message("そのアカウントは借りていません。", ephemeral=True)

@bot.tree.command(name="register")
async def register(interaction: discord.Interaction, name: str, account_id: str, password: str, rank: str):
    try:
        sheet.append_row([name, account_id, password, rank, "available", ""])
        await interaction.response.send_message(f"アカウント **{name}** を登録しました。", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"エラー: {e}", ephemeral=True)

# Bot起動
bot.run(os.environ["TOKEN"])
