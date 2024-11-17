import discord
from discord.ext import commands
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import os
import json
from flask import Flask
import threading

# Google Sheets API スコープの設定
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]

# 環境変数から Secret を取得し、認証情報を作成
credentials_data = json.loads(os.environ["CREDENTIALS_JSON"])
credentials = ServiceAccountCredentials.from_json_keyfile_dict(credentials_data, scope)

# Google Sheets に接続
gc = gspread.authorize(credentials)

# スプレッドシートを開く（シート名を指定）
spreadsheet_name = "Accounts"  # 変更してください
sheet = gc.open(spreadsheet_name).sheet1

# Bot の設定
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# Flask アプリのセットアップ（Koyeb のヘルスチェック用）
app = Flask(__name__)

@app.route("/")
def health_check():
    return "OK", 200

def run_server():
    app.run(host="0.0.0.0", port=8080)

server_thread = threading.Thread(target=run_server)
server_thread.daemon = True
server_thread.start()

# Bot が準備完了したときのイベント
@bot.event
async def on_ready():
    print(f'Logged in as {bot.user}')
    try:
        synced = await bot.tree.sync()
        print(f"スラッシュコマンドが {len(synced)} 個同期されました。")
    except Exception as e:
        print(f"同期中にエラーが発生しました: {e}")

# アカウントを借りたユーザーが新たにアカウントを借りられないようにするチェック
def can_borrow_account(user_id):
    for record in records:
        # borrowerキーが存在するかを確認し、存在しない場合は空文字を返す
        borrower = record.get("borrower", "")
        
        if borrower == str(user_id):
            return False  # すでに借りている
    return True  # 借りていない

# アカウントの登録コマンド
@bot.tree.command(name="register")
async def register(interaction: discord.Interaction, name: str, account_id: str, password: str, rank: str):
    # スプレッドシートに新しいアカウントを登録
    sheet.append_row([name, account_id, password, rank, "available", ""])
    await interaction.response.send_message(f"アカウント **{name}** が正常に登録されました。", ephemeral=True)

# アカウントを返却するコマンド
@bot.tree.command(name="return_account")
async def return_account(interaction: discord.Interaction, name: str, new_rank: str):
    user_id = str(interaction.user.id)
    records = sheet.get_all_records()
    for index, record in enumerate(records):
        if record["name"] == name and record["borrower"] == user_id:
            # アカウントのランクを更新し、状態を利用可能に設定
            sheet.update_cell(index + 2, 4, new_rank)  # ランクの列
            sheet.update_cell(index + 2, 5, "available")  # 状態の列
            sheet.update_cell(index + 2, 6, "")  # 借りたユーザーの列をクリア
            await interaction.response.send_message(f"アカウント **{name}** が返却され、ランクが更新されました。", ephemeral=True)
            return
    await interaction.response.send_message("アカウントの返却に失敗しました。指定されたアカウントを借りていない可能性があります。", ephemeral=True)

# アカウントを利用するコマンド
@bot.tree.command(name="use_account")
async def use_account(interaction: discord.Interaction):
    user_id = str(interaction.user.id)

    # アカウントを既に借りているかどうかをチェック
    if not can_borrow_account(user_id):
        await interaction.response.send_message("既にアカウントを借りています。返却してください。", ephemeral=True)
        return

    # 利用可能なアカウントを取得
    records = sheet.get_all_records()
    available_accounts = [record for record in records if record["status"] == "available"]

    if not available_accounts:
        await interaction.response.send_message("利用可能なアカウントがありません。", ephemeral=True)
        return

    # プルダウンメニューを表示
    class AccountSelectView(discord.ui.View):
        def __init__(self):
            super().__init__(timeout=None)
            self.account_selection = discord.ui.Select(
                placeholder="利用するアカウントを選んでください",
                options=[
                    discord.SelectOption(label=f"{account['name']} - {account['rank']}", value=account["name"])
                    for account in available_accounts
                ]
            )
            self.account_selection.callback = self.on_select_account
            self.add_item(self.account_selection)

        async def on_select_account(self, interaction: discord.Interaction):
            selected_account_name = self.account_selection.values[0]
            for index, record in enumerate(records):
                if record["name"] == selected_account_name:
                    # アカウントを貸し出し状態に更新
                    sheet.update_cell(index + 2, 5, "borrowed")
                    sheet.update_cell(index + 2, 6, user_id)
                    await interaction.response.send_message(
                        f"アカウント **{record['name']}** の詳細:\n"
                        f"**ID**: {record['id']}\n"
                        f"**パスワード**: {record['password']}\n"
                        f"**ランク**: {record['rank']}",
                        ephemeral=True
                    )
                    # 全体通知
                    channel = bot.get_channel(YOUR_CHANNEL_ID)  # 通知するチャンネル ID を設定
                    await channel.send(f"ユーザー <@{user_id}> がアカウント **{record['name']}** を借りました！")
                    return

    await interaction.response.send_message("利用するアカウントを選んでください:", view=AccountSelectView(), ephemeral=True)

# ヘルプコマンド
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

# Bot を実行
bot.run(os.environ["TOKEN"])  # Discord トークンは環境変数から取得
