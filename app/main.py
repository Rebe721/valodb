import os
import json
from oauth2client.service_account import ServiceAccountCredentials
import discord
from discord.ext import commands
from discord import app_commands
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
tree = bot.tree  # スラッシュコマンド用の管理クラス

# ユーザーの借用状態を保持
borrowed_accounts = {}
user_status = {}

# 登録コマンド
@tree.command(name="register", description="新しいアカウントを登録します")
async def register(interaction: discord.Interaction):
    # モーダルの作成
    modal = discord.ui.Modal(title="アカウント登録フォーム")

    # 各入力フィールドを追加
    modal.add_item(
        discord.ui.TextInput(
            label="Name",
            placeholder="例: Tanaka Taro",
            custom_id="account-name",
            required=True
        )
    )
    modal.add_item(
        discord.ui.TextInput(
            label="ID",
            placeholder="例: user123",
            custom_id="account-id",
            required=True
        )
    )
    modal.add_item(
        discord.ui.TextInput(
            label="Password",
            placeholder="例: ******",
            custom_id="account-password",
            required=True
        )
    )
    modal.add_item(
        discord.ui.TextInput(
            label="Rank",
            placeholder="例: Beginner",
            custom_id="account-rank",
            required=True
        )
    )

    # モーダル送信後の処理
    async def modal_callback(interaction_modal: discord.Interaction):
        name = interaction_modal.text_values["account-name"]
        account_id = interaction_modal.text_values["account-id"]
        password = interaction_modal.text_values["account-password"]
        rank = interaction_modal.text_values["account-rank"]

        # スプレッドシートに追加
        sheet.append_row([name, account_id, password, rank, "available"])
        await interaction_modal.response.send_message(
            f"アカウント {name} を登録しました！", ephemeral=True
        )

    modal.callback = modal_callback
    await interaction.response.send_modal(modal)

# アカウント選択コマンド
@tree.command(name="use_account", description="アカウントを借りる")
async def use_account(interaction: discord.Interaction):
    if interaction.user.id in user_status:
        await interaction.response.send_message(
            "すでにアカウントを借りています。返却してください。", ephemeral=True
        )
        return

    # スプレッドシートデータを取得し、行番号を追加
    accounts = sheet.get_all_records()
    available_accounts = [
        {**acc, "row": index + 2}  # 行番号を計算 (ヘッダー行を考慮)
        for index, acc in enumerate(accounts)
        if acc["status"] == "available"
    ]

    if not available_accounts:
        await interaction.response.send_message(
            "利用可能なアカウントがありません。", ephemeral=True
        )
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
            selected_account = next(
                acc for acc in available_accounts if acc["name"] == self.values[0]
            )
            # 'row' を利用して行を更新
            sheet.update_cell(selected_account["row"], 5, "borrowed")
            borrowed_accounts[interaction.user.id] = selected_account
            user_status[interaction.user.id] = True
            await interaction.response.send_message(
                f"アカウント {selected_account['name']} を借りました。\n"
                f"ID: {selected_account['id']}\n"
                f"Password: {selected_account['password']}\n"
                f"Rank: {selected_account['rank']}", 
                ephemeral=True
            )
            await interaction.channel.send(
                f"{interaction.user.name}が{selected_account['name']}を借りました！"
            )

    view = discord.ui.View()
    view.add_item(AccountDropdown())
    await interaction.response.send_message("アカウントを選択してください:", view=view, ephemeral=True)

# アカウント返却コマンド
@tree.command(name="return_account", description="アカウントを返却する")
async def return_account(interaction: discord.Interaction):
    if interaction.user.id not in borrowed_accounts:
        await interaction.response.send_message(
            "返却するアカウントがありません。", ephemeral=True
        )
        return

    account = borrowed_accounts.pop(interaction.user.id)
    user_status.pop(interaction.user.id)

    # ランクを入力するためのモーダルを作成
    class RankUpdateModal(discord.ui.Modal):
        def __init__(self):
            super().__init__(title="ランク更新フォーム")
            self.add_item(discord.ui.TextInput(
                label="New Rank",
                placeholder="例: Intermediate",
                custom_id="new-rank",
                required=True
            ))

        async def on_submit(self, interaction: discord.Interaction):
            new_rank = self.children[0].value
            # スプレッドシートのランク列を更新
            sheet.update_cell(account["row"], 4, new_rank)
            # ステータスを 'available' に更新
            sheet.update_cell(account["row"], 5, "available")
            await interaction.response.send_message(
                f"アカウント {account['name']} を返却し、ランクを {new_rank} に更新しました。", 
                ephemeral=True
            )
            await interaction.channel.send(
                f"{interaction.user.name}が{account['name']}を返却し、ランクを {new_rank} に更新しました！"
            )

    # モーダルを表示
    await interaction.response.send_modal(RankUpdateModal())

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

# Bot準備完了時のイベント
@bot.event
async def on_ready():
    await tree.sync()  # スラッシュコマンドを同期
    print(f"Logged in as {bot.user}")

# Discord Botを起動
TOKEN = os.getenv("TOKEN")
bot.run(TOKEN)
