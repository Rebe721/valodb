import os
import json
from oauth2client.service_account import ServiceAccountCredentials
import discord
from discord.ext import commands
import gspread
from flask import Flask

# GoogleスプレッドシートAPIのスコープ
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]

# 環境変数から認証情報を取得
credentials_info = json.loads(os.getenv("CREDENTIALS_JSON"))
credentials = ServiceAccountCredentials.from_json_keyfile_dict(credentials_info, scope)

# Googleスプレッドシートの設定
gc = gspread.authorize(credentials)
sheet = gc.open("Accounts").sheet1  # スプレッドシート名を設定

# Discord Botの設定
intents = discord.Intents.default()
intents.messages = True
intents.message_content = True
bot = commands.Bot(command_prefix="/", intents=intents)

# ユーザーの借用状態を保持
borrowed_accounts = {}
user_status = {}

# 登録コマンド
@bot.command()
async def register(ctx):
    def check(m):
        return m.author == ctx.author and m.channel == ctx.channel

    await ctx.send("Nameを入力してください:", ephemeral=True)
    name = (await bot.wait_for("message", check=check)).content

    await ctx.send("IDを入力してください:", ephemeral=True)
    account_id = (await bot.wait_for("message", check=check)).content

    await ctx.send("Passwordを入力してください:", ephemeral=True)
    password = (await bot.wait_for("message", check=check)).content

    await ctx.send("Rankを入力してください:", ephemeral=True)
    rank = (await bot.wait_for("message", check=check)).content

    # スプレッドシートに追加
    sheet.append_row([name, account_id, password, rank, "available"])
    await ctx.send(f"アカウント {name} を登録しました！", ephemeral=True)

# アカウント選択コマンド
@bot.command()
async def use_account(ctx):
    if ctx.author.id in user_status:
        await ctx.send("すでにアカウントを借りています。返却してください。", ephemeral=True)
        return

    accounts = sheet.get_all_records()
    available_accounts = [acc for acc in accounts if acc["status"] == "available"]

    if not available_accounts:
        await ctx.send("利用可能なアカウントがありません。", ephemeral=True)
        return

    # プルダウンメニューを作成
    options = [
        discord.SelectOption(label=f"{acc['name']} ({acc['rank']})", value=acc["name"])
        for acc in available_accounts
    ]

    class AccountDropdown(discord.ui.Select):
        def __init__(self):
            super().__init__(placeholder="アカウントを選択してください", options=options)

        async def callback(self, interaction: discord.Interaction):
            selected_account = next(acc for acc in available_accounts if acc["name"] == self.values[0])
            sheet.update_cell(selected_account["row"], 5, "borrowed")
            borrowed_accounts[ctx.author.id] = selected_account
            user_status[ctx.author.id] = True
            await interaction.response.send_message(
                f"アカウント {selected_account['name']} を借りました。", ephemeral=True
            )
            await ctx.channel.send(f"{ctx.author.name}が{selected_account['name']}を借りました！")

    view = discord.ui.View()
    view.add_item(AccountDropdown())
    await ctx.send("アカウントを選択してください:", view=view, ephemeral=True)

# アカウント返却コマンド
@bot.command()
async def return_account(ctx):
    if ctx.author.id not in borrowed_accounts:
        await ctx.send("返却するアカウントがありません。", ephemeral=True)
        return

    account = borrowed_accounts.pop(ctx.author.id)
    sheet.update_cell(account["row"], 5, "available")
    user_status.pop(ctx.author.id)
    await ctx.send(f"アカウント {account['name']} を返却しました。", ephemeral=True)
    await ctx.channel.send(f"{ctx.author.name}が{account['name']}を返却しました！")

# Flaskアプリケーションの設定 (ヘルスチェック用)
app = Flask(__name__)

@app.route("/health")
def health_check():
    return "OK", 200

# Discord Botを起動するスレッドとFlaskサーバーを同時に起動
from threading import Thread

def run_flask():
    app.run(host="0.0.0.0", port=8080)

# Flask サーバーをバックグラウンドで実行
thread = Thread(target=run_flask)
thread.daemon = True
thread.start()

# Discord Botを起動
TOKEN = os.getenv("TOKEN")
bot.run(TOKEN)
