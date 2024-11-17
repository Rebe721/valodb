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
    records = sheet.get_all_records()
    for record in records:
        # デバッグ用ログ
        print(f"チェック中のデータ: {record}")
        if str(record.get("borrower", "")) == str(user_id):
            return False
    return True

# アカウントの登録コマンド
@bot.tree.command(name="register")
async def register(interaction: discord.Interaction, name: str, account_id: str, password: str, rank: str):
    await interaction.response.defer(ephemeral=True)  # 一時保留
    try:
        sheet.append_row([name, account_id, password, rank, "available", ""])
        await interaction.followup.send(f"アカウント **{name}** が正常に登録されました。", ephemeral=True)
    except Exception as e:
        print(f"エラー: {e}")
        await interaction.followup.send("登録中にエラーが発生しました。", ephemeral=True)

# アカウントを返却するコマンド
@bot.tree.command(name="return_account")
async def return_account(interaction: discord.Interaction, name: str, new_rank: str):
    user_id = str(interaction.user.id)
    records = sheet.get_all_records()
    for index, record in enumerate(records):
        # デバッグ用ログ
        print(f"現在のデータ: {record}")
        if record.get("name", "").strip() == name and str(record.get("borrower", "")).strip() == user_id:
            try:
                # スプレッドシートの更新
                sheet.update_cell(index + 2, 4, new_rank)  # ランクを更新
                sheet.update_cell(index + 2, 5, "available")  # 状態を更新
                sheet.update_cell(index + 2, 6, "")  # 借り手をクリア
                await interaction.response.send_message(f"アカウント **{name}** が返却され、ランクが更新されました。", ephemeral=True)
                return
            except Exception as e:
                print(f"スプレッドシートの更新中にエラー: {e}")
                await interaction.response.send_message("アカウントの返却中にエラーが発生しました。", ephemeral=True)
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
    available_accounts = [record for record in records if record.get("status") == "available"]

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
                    try:
                        # アカウントを貸し出し状態に更新
                        sheet.update_cell(index + 2, 5, "borrowed")  # 状態を更新
                        sheet.update_cell(index + 2, 6, user_id)     # 借り手を更新
                        await interaction.response.send_message(
                            f"アカウント **{record['name']}** の詳細:\n"
                            f"**ID**: {record['account_id']}\n"
                            f"**パスワード**: {record['password']}\n"
                            f"**ランク**: {record['rank']}",
                            ephemeral=True
                        )
                        # 全体通知
                        channel = bot.get_channel(1307661467578925056)  # 通知するチャンネル ID を設定
                        if channel:
                            await channel.send(f"ユーザー <@{user_id}> がアカウント **{record['name']}** を借りました！")
                        else:
                            print("指定されたチャンネルが見つかりません。")
                        return
                    except Exception as e:
                        print(f"スプレッドシート更新エラー: {e}")
                        await interaction.response.send_message("アカウントの貸し出し中にエラーが発生しました。", ephemeral=True)
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
