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

                # 全体通知
                channel = bot.get_channel(1305414048187154474)  # 通知用チャンネルID
                if channel is not None:
                    await channel.send(f"ユーザー <@{user_id}> がアカウント **{name}** を返却しました！ 新ランク: {new_rank}")
                return
            except Exception as e:
                print(f"スプレッドシートの更新中にエラー: {e}")
                await interaction.response.send_message("アカウントの返却中にエラーが発生しました。", ephemeral=True)
                return
    await interaction.response.send_message("アカウントの返却に失敗しました。指定されたアカウントを借りていない可能性があります。", ephemeral=True)

# アカウント選択
class AccountSelectView(View):
    def __init__(self, user_id: str, records: list):
        super().__init__(timeout=900.0)  # タイムアウトを15分に設定
        self.user_id = user_id
        self.records = records

        # プルダウンメニューのオプションを生成
        self.account_selection = Select(
            placeholder="利用するアカウントを選んでください",
            min_values=1,
            max_values=1,
            options=[
                discord.SelectOption(label=record["name"], value=record["name"])
                for record in records
            ]
        )
        self.account_selection.callback = self.on_select_account
        self.add_item(self.account_selection)

    async def on_select_account(self, interaction: discord.Interaction):
        try:
            # 選択されたアカウントを取得
            selected_account_name = self.account_selection.values[0]

            # 該当するアカウントを検索
            for index, record in enumerate(self.records):
                if record["name"] == selected_account_name:
                    # アカウントの状態を更新
                    sheet.update_cell(index + 2, 5, "borrowed")  # 状態を "borrowed" に
                    sheet.update_cell(index + 2, 6, self.user_id)  # 借り手を設定

                    # 応答メッセージを送信
                    await interaction.response.send_message(
                        f"アカウント **{record['name']}** の詳細:\n"
                        f"**ID**: {record['id']}\n"
                        f"**パスワード**: {record['password']}\n"
                        f"**ランク**: {record['rank']}",
                        ephemeral=True
                    )

                    # 全体通知
                    channel = bot.get_channel(1305414048187154474)  # 通知用チャンネルID
                    if channel is not None:
                        await channel.send(f"ユーザー <@{self.user_id}> がアカウント **{record['name']}** を借りました！")
                    return

            # アカウントが見つからない場合
            await interaction.response.send_message("選択されたアカウントが見つかりませんでした。", ephemeral=True)
        except Exception as e:
            print(f"選択処理中のエラー: {e}")
            await interaction.response.send_message("アカウント選択中にエラーが発生しました。", ephemeral=True)

class AccountSelectView(View):
    def __init__(self, user_id: str, records: list):
        super().__init__(timeout=900.0)  # タイムアウトを15分に設定
        self.user_id = user_id
        self.records = records

        # プルダウンメニューのオプションを生成
        self.account_selection = Select(
            placeholder="利用するアカウントを選んでください",
            min_values=1,
            max_values=1,
            options=[
                discord.SelectOption(label=record["name"], value=str(index))
                for index, record in enumerate(records)
            ]
        )
        self.account_selection.callback = self.on_select_account
        self.add_item(self.account_selection)

    async def on_select_account(self, interaction: discord.Interaction):
        try:
            # 選択されたアカウントのインデックスを取得
            selected_index = int(self.account_selection.values[0])
            selected_account = self.records[selected_index]

            # すでに借りているアカウントがあるか確認
            current_borrowed = next(
                (record for record in self.records if record.get("borrower") == self.user_id),
                None
            )
            if current_borrowed:
                await interaction.response.send_message(
                    f"あなたは既にアカウント **{current_borrowed['name']}** を借りています。返却してください。",
                    ephemeral=True
                )
                return

            # スプレッドシートの更新
            sheet.update_cell(selected_index + 2, 5, "borrowed")  # 状態を "borrowed" に
            sheet.update_cell(selected_index + 2, 6, self.user_id)  # 借り手を設定

            # 応答メッセージを送信
            await interaction.response.send_message(
                f"アカウント **{selected_account['name']}** の詳細:\n"
                f"**ID**: {selected_account['id']}\n"
                f"**パスワード**: {selected_account['password']}\n"
                f"**ランク**: {selected_account['rank']}",
                ephemeral=True
            )

            # 全体通知
            channel = bot.get_channel(1307661467578925056)  # 通知用チャンネルID
            if channel is not None:
                await channel.send(f"ユーザー <@{self.user_id}> がアカウント **{selected_account['name']}** を借りました！")
        except Exception as e:
            print(f"選択処理中のエラー: {e}")
            await interaction.response.send_message("アカウント選択中にエラーが発生しました。", ephemeral=True)

# アカウント利用
@bot.tree.command(name="use_account")
async def use_account(interaction: discord.Interaction):
    user_id = str(interaction.user.id)
    records = sheet.get_all_records()

    # ユーザーがすでに借りているアカウントを確認
    borrowed_account = next((record for record in records if record.get("borrower") == user_id), None)
    if borrowed_account:
        await interaction.response.send_message(
            f"あなたは既にアカウント **{borrowed_account['name']}** を借りています。返却してください。",
            ephemeral=True
        )
        return

    # 利用可能なアカウントを取得
    available_accounts = [record for record in records if record.get("status") == "available"]
    if not available_accounts:
        await interaction.response.send_message("利用可能なアカウントがありません。", ephemeral=True)
        return

    # アカウント選択メニューを表示
    await interaction.response.send_message(
        "利用するアカウントを選んでください:",
        view=AccountSelectView(user_id, available_accounts),
        ephemeral=True
    )


# ボット起動時の処理
@bot.event
async def on_ready():
    print(f"{bot.user} がログインしました!")

# ボットの起動
bot.run(os.environ["TOKEN"])  # Discordトークンは環境変数から取得
