import discord
from discord.ext import commands
from googleapiclient.discovery import build
from google.oauth2.service_account import Credentials
import os

# Google Sheets API設定
SCOPES = ['https://www.googleapis.com/auth/spreadsheets']
SPREADSHEET_ID = "1_xEKOwz4WsYv7C4bQRpwuRl4AOJnokFZktVpB9yIRCc"  
RANGE_NAME = "Accounts!A2:F"  

# Google認証の読み込み
credentials = Credentials.from_service_account_file('credentials.json', scopes=SCOPES)
service = build('sheets', 'v4', credentials=credentials)

# Bot設定
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# Bot準備完了時
@bot.event
async def on_ready():
    print(f'Logged in as {bot.user}')
    try:
        synced = await bot.tree.sync()
        print(f"スラッシュコマンドが {len(synced)} 個同期されました。")
    except Exception as e:
        print(f"同期中にエラーが発生しました: {e}")

# アカウント登録コマンド
@bot.tree.command(name="register")
async def register(interaction: discord.Interaction, name: str, account_id: str, password: str, rank: str):
    # Google Sheetsにアカウントを追加
    values = [[name, account_id, password, rank, "available", ""]]
    body = {"values": values}
    service.spreadsheets().values().append(
        spreadsheetId=SPREADSHEET_ID, range=RANGE_NAME,
        valueInputOption="RAW", body=body
    ).execute()

    await interaction.response.send_message(f"アカウント **{name}** が正常に登録されました。", ephemeral=True)

# アカウント利用コマンド
@bot.tree.command(name="use_account")
async def use_account(interaction: discord.Interaction):
    # Google Sheetsから利用可能なアカウントを取得
    result = service.spreadsheets().values().get(
        spreadsheetId=SPREADSHEET_ID, range=RANGE_NAME
    ).execute()
    rows = result.get('values', [])
    available_accounts = [row for row in rows if len(row) > 4 and row[4] == "available"]

    if not available_accounts:
        await interaction.response.send_message("利用可能なアカウントがありません。", ephemeral=True)
        return

    options = [
        discord.SelectOption(label=f"{row[0]} ({row[3]})", value=row[0]) for row in available_accounts
    ]

    select = discord.ui.Select(placeholder="利用するアカウントを選んでください", options=options)

    async def callback(interaction: discord.Interaction):
        selected_account = select.values[0]
        for row in rows:
            if row[0] == selected_account:
                row[4] = "borrowed"
                row[5] = str(interaction.user.id)
                service.spreadsheets().values().update(
                    spreadsheetId=SPREADSHEET_ID, range=RANGE_NAME,
                    valueInputOption="RAW", body={"values": rows}
                ).execute()
                await interaction.response.send_message(
                    f"{interaction.user.name} が **{selected_account}** を借りました！", ephemeral=False
                )
                break

    view = discord.ui.View()
    select.callback = callback
    view.add_item(select)
    await interaction.response.send_message("利用するアカウントを選んでください:", view=view, ephemeral=True)

# アカウント返却コマンド
@bot.tree.command(name="return_account")
async def return_account(interaction: discord.Interaction, name: str):
    # Google Sheetsからデータを取得
    result = service.spreadsheets().values().get(
        spreadsheetId=SPREADSHEET_ID, range=RANGE_NAME
    ).execute()
    rows = result.get('values', [])

    for row in rows:
        if row[0] == name and len(row) > 5 and row[5] == str(interaction.user.id):
            row[4] = "available"
            row[5] = ""
            service.spreadsheets().values().update(
                spreadsheetId=SPREADSHEET_ID, range=RANGE_NAME,
                valueInputOption="RAW", body={"values": rows}
            ).execute()
            await interaction.response.send_message(f"アカウント **{name}** を返却しました。", ephemeral=True)
            return

    await interaction.response.send_message("アカウントの返却に失敗しました。", ephemeral=True)

# Bot起動
bot.run(os.environ['TOKEN'])
