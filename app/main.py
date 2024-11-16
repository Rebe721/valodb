import discord
from discord.ext import commands
from googleapiclient.discovery import build
from google.oauth2.service_account import Credentials
import json
import os

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

# Bot起動
bot.run(os.environ['TOKEN'])
