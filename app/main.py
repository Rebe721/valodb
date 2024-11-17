import discord
from discord.ext import commands
from discord.ui import View, Select
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import os
import json
from flask import Flask
import threading

# Flask アプリのセットアップ（Koyebのヘルスチェック用）
app = Flask(__name__)

@app.route("/")
def health_check():
    return "OK", 200

def run_server():
    app.run(host="0.0.0.0", port=8080)

server_thread = threading.Thread(target=run_server)
server_thread.daemon = True
server_thread.start()

# Google Sheets APIとの接続設定
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
credentials_data = json.loads(os.environ["CREDENTIALS_JSON"])
credentials = ServiceAccountCredentials.from_json_keyfile_dict(credentials_data, scope)
gc = gspread.authorize(credentials)
sheet = gc.open("Accounts").sheet1  # アカウントデータのシート

# ボットの設定
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# アカウント登録
@bot.tree.command(name="register")
async def register(interaction: discord.Interaction, name: str, account_id: str, password: str, rank: str):
    try:
        # スプレッドシートに新しいアカウントを登録
        sheet.append_row([name, account_id, password, rank, "available", ""])
        await interaction.response.send_message(f"アカウント **{name}** が正常に登録されました。", ephemeral=True)
    except discord.errors.NotFound:
        await interaction.followup.send(f"アカウント **{name}** が正常に登録されました。（応答が遅延した可能性があります）", ephemeral=True)

# アカウント返却
@bot.tree.command(name="return_account")
async def return_account(interaction: discord.Interaction, name: str, new_rank: str):
    user_id = str(interaction.user.id)
    records = sheet.get_all_records()
    for index, record in enumerate(records):
        borrower = str(record.get("borrower", ""))
        if record.get("name", "").strip() == name and borrower.strip() == user_id:
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

# アカウント選択
class AccountSelectView(View):
    def __init__(self, user_id: str, records: list):
        super().__init__(timeout=900.0)
        self.user_id = user_id
        self.records = records
        self.account_selection = Select(placeholder="利用するアカウントを選んでください", min_values=1, max_values=1, options=[])
        for record in records:
            self.account_selection.add_option(label=record["name"], value=record["name"])
        self.add_item(self.account_selection)

    async def on_select_account(self, interaction: discord.Interaction):
        selected_account_name = self.account_selection.values[0]
        for index, record in enumerate(self.records):
            if record["name"] == selected_account_name:
                sheet.update_cell(index + 2, 5, "borrowed")
                sheet.update_cell(index + 2, 6, self.user_id)
                await interaction.response.send_message(
                    f"アカウント **{record['name']}** の詳細:\n"
                    f"**ID**: {record['id']}\n"
                    f"**パスワード**: {record['password']}\n"
                    f"**ランク**: {record['rank']}",
                    ephemeral=True
                )
                # 通知用チャンネル
                channel = bot.get_channel(1307661467578925056)  # チャンネルIDが正しいことを確認
                if channel is not None:
                    try:
                        await channel.send(f"ユーザー <@{self.user_id}> がアカウント **{record['name']}** を借りました！")
                    except discord.errors.Forbidden:
                        print(f"通知を送信できません。チャンネルのアクセス権限を確認してください。")
                return

# アカウント利用
@bot.tree.command(name="use_account")
async def use_account(interaction: discord.Interaction):
    user_id = str(interaction.user.id)
    records = sheet.get_all_records()
    available_accounts = [record for record in records if record.get("status") == "available"]
    if not available_accounts:
        await interaction.response.send_message("利用可能なアカウントがありません。", ephemeral=True)
        return
    await interaction.response.send_message("利用するアカウントを選んでください:", view=AccountSelectView(user_id, available_accounts), ephemeral=True)

# ボット起動時の処理
@bot.event
async def on_ready():
    print(f"{bot.user} がログインしました!")

# ボットの起動
bot.run(os.environ["TOKEN"])  # Discordトークンは環境変数から取得
