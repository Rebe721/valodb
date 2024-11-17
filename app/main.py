import discord
from discord.ext import commands
from googleapiclient.discovery import build
from google.oauth2.service_account import Credentials
import json
import os
import threading
from flask import Flask

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
credentials_info = json.loads(os.environ["CREDENTIALS_JSON"])
credentials = Credentials.from_service_account_info(credentials_info, scopes=SCOPES)
service = build('sheets', 'v4', credentials=credentials)

SPREADSHEET_ID = "1_xEKOwz4WsYv7C4bQRpwuRl4AOJnokFZktVpB9yIRCc"  

# Discord Bot設定
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# スプレッドシート操作関数
def get_sheet_data():
    sheet = service.spreadsheets()
    result = sheet.values().get(spreadsheetId=SPREADSHEET_ID, range="Accounts!A2:F").execute()
    return result.get('values', [])

def update_sheet_data(row_index, values):
    sheet = service.spreadsheets()
    sheet.values().update(
        spreadsheetId=SPREADSHEET_ID,
        range=f"Accounts!A{row_index + 2}:F",
        valueInputOption="RAW",
        body={"values": [values]}
    ).execute()

# アカウント利用可能チェック
def can_borrow_account(user_id):
    rows = get_sheet_data()
    return all(row[5] != str(user_id) for row in rows if len(row) >= 6)

# Bot準備完了イベント
@bot.event
async def on_ready():
    print(f'Logged in as {bot.user}')

# スラッシュコマンド: アカウント登録
@bot.tree.command(name="register")
async def register(interaction: discord.Interaction, name: str, account_id: str, password: str, rank: str):
    sheet = service.spreadsheets()
    new_account = [name, account_id, password, rank, "available", ""]
    rows = get_sheet_data()
    sheet.values().append(
        spreadsheetId=SPREADSHEET_ID,
        range="Accounts!A2:F",
        valueInputOption="RAW",
        body={"values": [new_account]}
    ).execute()
    await interaction.response.send_message(f"アカウント **{name}** が登録されました。", ephemeral=True)

# スラッシュコマンド: アカウント利用
@bot.tree.command(name="use_account")
async def use_account(interaction: discord.Interaction):
    user_id = str(interaction.user.id)
    if not can_borrow_account(user_id):
        await interaction.response.send_message("既にアカウントを借りています。返却してください。", ephemeral=True)
        return

    rows = get_sheet_data()
    available_accounts = [row for row in rows if len(row) >= 5 and row[4] == "available"]

    if not available_accounts:
        await interaction.response.send_message("利用可能なアカウントがありません。", ephemeral=True)
        return

    options = [
        discord.SelectOption(label=f"{row[0]} - {row[3]}", value=row[0])
        for row in available_accounts
    ]

    class AccountSelectView(discord.ui.View):
        @discord.ui.select(placeholder="利用するアカウントを選んでください", options=options)
        async def select_account(self, select, interaction):
            selected_name = select.values[0]
            for i, row in enumerate(rows):
                if row[0] == selected_name:
                    updated_values = [selected_name, row[1], row[2], row[3], "borrowed", user_id]
                    update_sheet_data(i, updated_values)
                    break

            await interaction.response.send_message(
                f"アカウント **{selected_name}** を借りました。詳細は以下の通りです:\n"
                f"**ID**: {row[1]}\n**Password**: {row[2]}\n**Rank**: {row[3]}",
                ephemeral=True
            )
            await interaction.channel.send(f"**{interaction.user.name}** がアカウント **{selected_name}** を借りました！")

    await interaction.response.send_message("利用するアカウントを選んでください:", view=AccountSelectView(), ephemeral=True)

# スラッシュコマンド: アカウント返却
@bot.tree.command(name="return_account")
async def return_account(interaction: discord.Interaction, name: str, new_rank: str):
    user_id = str(interaction.user.id)
    rows = get_sheet_data()
    for i, row in enumerate(rows):
        if row[0] == name and len(row) >= 6 and row[5] == user_id:
            updated_values = [name, row[1], row[2], new_rank, "available", ""]
            update_sheet_data(i, updated_values)
            await interaction.response.send_message(f"アカウント **{name}** を返却しました。ランクは **{new_rank}** に更新されました。", ephemeral=True)
            return

    await interaction.response.send_message("指定されたアカウントを借りていないか、名前が間違っています。", ephemeral=True)

# スラッシュコマンド: ヘルプ
@bot.tree.command(name="helplist")
async def helplist(interaction: discord.Interaction):
    help_message = """
    **利用可能なコマンド:**

    **/register <名前> <ID> <パスワード> <ランク>**  
    アカウントを登録します。

    **/use_account**  
    利用可能なアカウントから選択して使用します。

    **/return_account <名前> <新しいランク>**  
    使用中のアカウントを返却し、ランクを更新します。
    """
    await interaction.response.send_message(help_message, ephemeral=True)

# Bot起動
bot.run(os.environ['TOKEN'])
