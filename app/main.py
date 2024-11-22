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

# カスタムモーダルクラス
class AccountRegisterModal(discord.ui.Modal):
    def __init__(self):
        super().__init__(title="アカウント登録フォーム")
        self.add_item(discord.ui.TextInput(
            label="Name",
            placeholder="例: Tanaka Taro",
            custom_id="account-name",
            required=True
        ))
        self.add_item(discord.ui.TextInput(
            label="ID",
            placeholder="例: user123",
            custom_id="account-id",
            required=True
        ))
        self.add_item(discord.ui.TextInput(
            label="Password",
            placeholder="例: ******",
            custom_id="account-password",
            required=True
        ))
        self.add_item(discord.ui.TextInput(
            label="Rank",
            placeholder="例: Beginner",
            custom_id="account-rank",
            required=True
        ))

    async def on_submit(self, interaction: discord.Interaction):
        name = self.children[0].value
        account_id = self.children[1].value
        password = self.children[2].value
        rank = self.children[3].value

        # スプレッドシートに追加
        sheet.append_row([name, account_id, password, rank, "available"])
        await interaction.response.send_message(
            f"アカウント {name} を登録しました！", ephemeral=True
        )

# 登録コマンド
@tree.command(name="register", description="新しいアカウントを登録します")
async def register(interaction: discord.Interaction):
    await interaction.response.send_modal(AccountRegisterModal())

# アカウント選択コマンド
# アカウント選択コマンド (詳細情報の送信を追加)
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

            # 選択したアカウントの詳細を表示
            account_details = (
                f"**アカウント情報:**\n"
                f"**Name:** {selected_account['name']}\n"
                f"**ID:** {selected_account['id']}\n"
                f"**Password:** {selected_account['password']}\n"
                f"**Rank:** {selected_account['rank']}\n"
            )
            await interaction.response.send_message(account_details, ephemeral=True)
            await interaction.channel.send(
                f"{interaction.user.name}が{selected_account['name']}を借りました！"
            )

    view = discord.ui.View()
    view.add_item(AccountDropdown())
    await interaction.response.send_message("アカウントを選択してください:", view=view, ephemeral=True)


# アカウント返却コマンド (ランク更新を追加)
@tree.command(name="return_account", description="アカウントを返却する")
async def return_account(interaction: discord.Interaction):
    if interaction.user.id not in borrowed_accounts:
        await interaction.response.send_message(
            "返却するアカウントがありません。", ephemeral=True
        )
        return

    account = borrowed_accounts.pop(interaction.user.id)

    class RankUpdateModal(discord.ui.Modal):
        def __init__(self):
            super().__init__(title="ランク更新")
            self.add_item(discord.ui.TextInput(
                label="新しいランクを入力 (例: Intermediate)",
                placeholder="変更がなければ同じランクを入力してください",
                default=account["rank"],
                custom_id="new-rank",
                required=True
            ))

        async def on_submit(self, interaction: discord.Interaction):
            new_rank = self.children[0].value
            if new_rank != account["rank"]:
                # スプレッドシートのランクセルを更新
                sheet.update_cell(account["row"], 4, new_rank)

            sheet.update_cell(account["row"], 5, "available")
            user_status.pop(interaction.user.id)
            await interaction.response.send_message(
                f"アカウント {account['name']} を返却しました。\n**新しいランク:** {new_rank}",
                ephemeral=True
            )
            await interaction.channel.send(
                f"{interaction.user.name}が{account['name']}を返却しました！\n**更新後のランク**:{new_rank}"
            )

    # ランク更新モーダルを表示
    await interaction.response.send_modal(RankUpdateModal())

@bot.command()
async def remove_comment(ctx):
    """テキストチャネル内のコメントを削除するコマンド"""
    if not ctx.author.guild_permissions.manage_messages:
        await ctx.send("このコマンドを使用する権限がありません。")
        return

    def is_comment(message):
        # コードブロック、画像、ファイルを含むメッセージを削除対象から除外
        has_codeblock = "```" in message.content
        has_attachment = message.attachments
        has_embeds = message.embeds
        return not (has_codeblock or has_attachment or has_embeds)

    # 現在のチャンネルのすべてのメッセージを取得し、条件に基づき削除
    deleted_count = 0
    async for message in ctx.channel.history(limit=100):  # 必要に応じてlimitを調整
        if message.author == bot.user:  # 自分のメッセージを除外
            continue
        if is_comment(message):
            await message.delete()
            deleted_count += 1

    await ctx.send(f"コメントを {deleted_count} 件削除しました！")

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
