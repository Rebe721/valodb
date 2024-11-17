import discord
from discord.ext import commands
from googleapiclient.discovery import build
from google.oauth2.service_account import Credentials
import json
import os
import threading
from flask import Flask
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from keep_alive import keep_alive  # Replitでサーバーを保持するためのモジュール

# Flask アプリを作成
app = Flask(__name__)

@app.route("/")
def health_check():
    return "OK", 200

# Flask サーバーをバックグラウンドで起動
def run_server():
    app.run(host="0.0.0.0", port=8080)

server_thread = threading.Thread(target=run_server)
server_thread.daemon = True
server_thread.start()

# Google Sheets API設定
SCOPES = ['https://www.googleapis.com/auth/spreadsheets']
credentials_info = json.loads(os.environ["CREDENTIALS_JSON"])  # 環境変数から認証情報を取得
credentials = Credentials.from_service_account_info(credentials_info, scopes=SCOPES)
service = build('sheets', 'v4', credentials=credentials)

SPREADSHEET_ID = "1_xEKOwz4WsYv7C4bQRpwuRl4AOJnokFZktVpB9yIRCc"  

# Discord Bot設定
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# スプレッドシートのデータを取得
def get_available_accounts():
    sheet = service.spreadsheets()
    result = sheet.values().get(spreadsheetId=SPREADSHEET_ID, range="Accounts!A2:F").execute()
    rows = result.get('values', [])
    return [row for row in rows if len(row) >= 5 and row[4] == "available"]

# アカウントを更新する（借りる/返却）
def update_account_status(name, status, borrower=None):
    sheet = service.spreadsheets()
    result = sheet.values().get(spreadsheetId=SPREADSHEET_ID, range="Accounts!A2:F").execute()
    rows = result.get('values', [])
    for i, row in enumerate(rows, start=2):
        if len(row) >= 1 and row[0] == name:
            update_values = [name, row[1], row[2], row[3], status, borrower or ""]
            sheet.values().update(
                spreadsheetId=SPREADSHEET_ID,
                range=f"Accounts!A{i}:F",
                valueInputOption="RAW",
                body={"values": [update_values]}
            ).execute()
            break

# Bot準備完了イベント
@bot.event
async def on_ready():
    print(f'Logged in as {bot.user}')

# アカウントを借りるコマンド
@bot.tree.command(name="use_account")
async def use_account(interaction: discord.Interaction):
    available_accounts = get_available_accounts()
    if not available_accounts:
        await interaction.response.send_message("利用可能なアカウントがありません。", ephemeral=True)
        return

    options = [
        discord.SelectOption(label=f"{row[0]} - {row[3]}", value=row[0])
        for row in available_accounts
    ]
    if not options:
        await interaction.response.send_message("利用可能なアカウントがありません。", ephemeral=True)
        return

    class AccountSelectView(discord.ui.View):
        @discord.ui.select(placeholder="利用するアカウントを選んでください", options=options)
        async def select_callback(self, select, interaction):
            selected_account = select.values[0]
            update_account_status(selected_account, "borrowed", str(interaction.user.id))
            await interaction.response.send_message(
                f"{interaction.user.mention}が**{selected_account}**を借りました！", ephemeral=True
            )
            await interaction.channel.send(f"{interaction.user.mention} が **{selected_account}** を借りました！")

    await interaction.response.send_message("利用するアカウントを選んでください:", view=AccountSelectView(), ephemeral=True)

# アカウントを返却するコマンド
@bot.tree.command(name="return_account")
async def return_account(interaction: discord.Interaction, name: str, new_rank: str):
    update_account_status(name, "available")
    await interaction.response.send_message(f"アカウント **{name}** を返却しました。ランクが更新されました。", ephemeral=True)

# ヘルプコマンド
@bot.tree.command(name="helplist")
async def helplist(interaction: discord.Interaction):
    help_message = """
    **利用可能なコマンド:**

    **/use_account**  
    利用可能なアカウントから選択して使用します。

    **/return_account <名前> <新しいランク>**  
    使用中のアカウントを返却し、ランクを更新します。
    """
    await interaction.response.send_message(help_message, ephemeral=True)

# Google スプレッドシートの認証設定（oauth2clientからgoogle-authに変更）
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
credentials_info = json.loads(os.environ["CREDENTIALS_JSON"])  # 環境変数から認証情報を取得
credentials = Credentials.from_service_account_info(credentials_info, scopes=scope)  # google-authを使用
gc = gspread.authorize(credentials)

# スプレッドシートを取得
sheet = gc.open("Accounts").sheet1  # "Accounts" をスプレッドシートの名前に変更してください

# アカウントを借りたユーザーが新たにアカウントを借りられないようにするチェック
def can_borrow_account(user_id):
    records = sheet.get_all_records()
    for record in records:
        if record["Borrower"] == str(user_id):
            return False
    return True

# スラッシュコマンド: アカウント登録
@bot.tree.command(name="register")
async def register(interaction: discord.Interaction, name: str, account_id: str, password: str, rank: str):
    try:
        # スプレッドシートに新しいアカウントを登録
        sheet.append_row([name, account_id, password, rank, "available", ""])
        # インタラクションが無効になっていないか確認
        if interaction.response.is_done():
            return
        await interaction.response.send_message(f"アカウント **{name}** が正常に登録されました。", ephemeral=True)
    except discord.errors.NotFound:
        # インタラクションが無効です
        print("インタラクションが無効です")

# スラッシュコマンド: アカウント利用
@bot.tree.command(name="use_account")
async def use_account(interaction: discord.Interaction):
    user_id = str(interaction.user.id)

    # 既にアカウントを借りているか確認
    if not can_borrow_account(user_id):
        await interaction.response.send_message("既にアカウントを借りています。返却してください。", ephemeral=True)
        return

    # 利用可能なアカウントを取得
    records = sheet.get_all_records()
    available_accounts = [record for record in records if record["Status"] == "available"]

    if not available_accounts:
        await interaction.response.send_message("現在利用可能なアカウントがありません。", ephemeral=True)
        return

    # アカウントリストを作成して送信
    options = [
        discord.SelectOption(label=f"{record['Name']} - {record['Rank']}", value=record["Name"])
        for record in available_accounts
    ]

    class AccountSelectView(discord.ui.View):
        @discord.ui.select(placeholder="利用するアカウントを選んでください", options=options)
        async def select_account(self, select, interaction):
            selected_name = select.values[0]
            for i, record in enumerate(records):
                if record["Name"] == selected_name:
                    sheet.update_cell(i + 2, 5, "borrowed")  # Status列を更新
                    sheet.update_cell(i + 2, 6, str(user_id))  # Borrower列を更新
                    break

            # 全体通知
            await interaction.channel.send(f"**{interaction.user.name}** がアカウント **{selected_name}** を借りました！")

            await interaction.response.send_message(
                f"アカウント **{selected_name}** を借りました。詳細は以下の通りです:\n"
                f"**ID**: {record['ID']}\n"
                f"**Password**: {record['Password']}\n"
                f"**Rank**: {record['Rank']}",
                ephemeral=True
            )

    await interaction.response.send_message("利用するアカウントを選んでください:", view=AccountSelectView(), ephemeral=True)

# スラッシュコマンド: アカウント返却
@bot.tree.command(name="return_account")
async def return_account(interaction: discord.Interaction, name: str, new_rank: str):
    user_id = str(interaction.user.id)

    # 該当アカウントを検索し、借りているか確認
    records = sheet.get_all_records()
    for i, record in enumerate(records):
        if record["Name"] == name and record["Borrower"] == user_id:
            sheet.update_cell(i + 2, 5, "available")
            sheet.update_cell(i + 2, 6, "")  # Borrower欄を空にする
            sheet.update_cell(i + 2, 4, new_rank)  # Rank更新
            await interaction.response.send_message(f"アカウント **{name}** を返却し、ランクを更新しました。", ephemeral=True)
            return

    await interaction.response.send_message("そのアカウントは借りていません。", ephemeral=True)

# Botを起動
keep_alive()  # Replitの場合にサーバーを維持
bot.run(os.environ["TOKEN"])
