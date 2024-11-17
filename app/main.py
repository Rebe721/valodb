import gspread
from oauth2client.service_account import ServiceAccountCredentials
import discord
from discord.ext import commands

# サービスアカウント認証
credentials = ServiceAccountCredentials.from_json_keyfile_name('path_to_credentials.json', ['https://spreadsheets.google.com/feeds'])
gc = gspread.authorize(credentials)

# スプレッドシートを開く
spreadsheet_name = 'Accounts'
sheet = gc.open(spreadsheet_name).sheet1

# ボットの設定
intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

# アカウントの登録時に使う関数
def register_account(user_id, account_name):
    # スプレッドシートに新しいアカウント情報を登録
    sheet.append_row([user_id, account_name, ""])  # borrower カラムは空にして登録

# アカウントを借りられるか確認する関数
def can_borrow_account(user_id):
    # スプレッドシートの全データを取得
    records = sheet.get_all_records()
    
    for record in records:
        # 'borrower' カラムを参照
        if record.get("borrower") == str(user_id):
            return False  # ユーザーがすでに借りている場合
    return True  # ユーザーが借りていない場合

# アカウントを使用するコマンド
@bot.tree.command(name="use_account", description="アカウントを借りる")
async def use_account(interaction: discord.Interaction):
    user_id = str(interaction.user.id)
    
    # アカウントを借りることができるかを確認
    if not can_borrow_account(user_id):
        await interaction.response.send_message(f"{interaction.user.name}さんは既にアカウントを借りています。")
        return
    
    # 借りる処理
    # ここに借りるアカウントの選択やその他の処理を実装することができます
    await interaction.response.send_message(f"{interaction.user.name}さんはアカウントを借りました。")

# 返却時の処理
@bot.tree.command(name="return_account", description="アカウントを返却する")
async def return_account(interaction: discord.Interaction, account_name: str):
    user_id = str(interaction.user.id)
    
    # アカウント返却処理
    records = sheet.get_all_records()
    for i, record in enumerate(records):
        if record.get("account_name") == account_name and record.get("borrower") == user_id:
            # borrower を空に設定して返却
            sheet.update_cell(i + 2, record.index("borrower") + 1, "")  # borrower カラムを空に更新
            await interaction.response.send_message(f"{interaction.user.name}さんが{account_name}を返却しました！")
            return True
    
    await interaction.response.send_message(f"{interaction.user.name}さんが借りているアカウントは見つかりませんでした。")
    return False

# botの起動
@bot.event
async def on_ready():
    print(f'We have logged in as {bot.user}')

bot.run("YOUR_DISCORD_BOT_TOKEN")
