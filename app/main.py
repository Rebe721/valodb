import discord
from discord.ext import commands
import gspread
import os
import json
from google.oauth2.service_account import Credentials
from discord.ui import View, Select, Button

# Google Sheetsのスプレッドシートキー
SPREADSHEET_ID = "1_xEKOwz4WsYv7C4bQRpwuRl4AOJnokFZktVpB9yIRCc"  # あなたのスプレッドシートのIDをここに設定してください
WORKSHEET_NAME = "Discord_database"  # シート名を設定してください

# Google API認証
json_key = os.environ.get('CREDENTIALS_JSON')  # 環境変数からCREDENTIALS_JSONを取得

if json_key:
    credentials = Credentials.from_service_account_info(json.loads(json_key), scopes=["https://www.googleapis.com/auth/spreadsheets"])
else:
    print("CREDENTIALS_JSON 環境変数が設定されていません")
    exit(1)

# Google Sheetsに接続
gc = gspread.authorize(credentials)
spreadsheet = gc.open_by_key(SPREADSHEET_ID)
worksheet = spreadsheet.worksheet(WORKSHEET_NAME)

# Botの設定
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# アカウントが借りられるかどうかを確認
def can_borrow_account(user_id):
    records = worksheet.get_all_records()
    for record in records:
        if record["borrower"] == str(user_id):
            return False
    return True

# アカウントを借りるためのView
class AccountSelectView(View):
    def __init__(self, user_id):
        super().__init__(timeout=None)
        if not can_borrow_account(user_id):
            self.add_item(Button(label="すでにアカウントを借りています。", disabled=True))
            return

        available_accounts = []
        records = worksheet.get_all_records()
        for record in records:
            if record["status"] == "available":
                available_accounts.append((record["name"], record["rank"]))

        # ソート処理（アルファベット順、数字順）
        sorted_accounts = sorted(available_accounts, key=lambda account: (account[0][0].lower(), int(''.join(filter(str.isdigit, account[0])) or 0)), reverse=True)

        # プルダウンメニューの作成
        self.account_selection = Select(
            placeholder="利用するアカウントを選んでください",
            options=[discord.SelectOption(label=f"{account[0]} - {account[1]}", value=account[0]) for account in sorted_accounts]
        )
        self.account_selection.callback = self.on_select_account
        self.add_item(self.account_selection)

    async def on_select_account(self, interaction: discord.Interaction):
        selected_account_name = self.account_selection.values[0]

        # スプレッドシートからアカウント情報を取得
        records = worksheet.get_all_records()
        account_details = None
        for record in records:
            if record["name"] == selected_account_name:
                account_details = record
                break

        # アカウント情報を更新して返却
        if account_details:
            worksheet.update_cell(records.index(account_details) + 2, 5, str(interaction.user.id))  # borrowerカラム更新
            worksheet.update_cell(records.index(account_details) + 2, 4, "borrowed")  # statusをborrowedに更新

            await interaction.response.send_message(
                f"選択されたアカウントの詳細:\n"
                f"**名前**: {account_details['name']}\n"
                f"**ID**: {account_details['id']}\n"
                f"**パスワード**: {account_details['password']}\n"
                f"**ランク**: {account_details['rank']}",
                ephemeral=True
            )
            await interaction.followup.send(f"{interaction.user.name} がアカウント **{selected_account_name}** を借りました！", ephemeral=False)
        else:
            await interaction.response.send_message("アカウント情報の取得に失敗しました。", ephemeral=True)

# アカウントを登録するコマンド
@bot.tree.command(name="register")
async def register(interaction: discord.Interaction, name: str, account_id: str, password: str, rank: str):
    # スプレッドシートにアカウントを追加
    new_row = [name, account_id, password, rank, "available", ""]  # 初期状態はavailableでborrowerは空白
    worksheet.append_row(new_row)

    # 完了メッセージを送信
    await interaction.response.send_message(f"アカウント **{name}** が正常に登録されました。", ephemeral=True)

# アカウントを返却するコマンド
@bot.tree.command(name="return_account")
async def return_account(interaction: discord.Interaction, name: str, new_rank: str):
    user_id = str(interaction.user.id)

    # スプレッドシートで該当アカウントを確認
    records = worksheet.get_all_records()
    account = None
    for record in records:
        if record["name"] == name and record["borrower"] == user_id:
            account = record
            break

    if account:
        # アカウントの状態とランクを更新
        worksheet.update_cell(records.index(account) + 2, 4, new_rank)  # ランク更新
        worksheet.update_cell(records.index(account) + 2, 5, "")  # borrowerを空白に
        worksheet.update_cell(records.index(account) + 2, 6, "available")  # 状態をavailableに戻す

        await interaction.response.send_message(f"アカウント **{name}** が返却され、ランクが更新されました。", ephemeral=True)
        await interaction.followup.send(f"{interaction.user.name} がアカウント **{name}** を返却しました！", ephemeral=False)
    else:
        await interaction.response.send_message("アカウントの返却に失敗しました。指定されたアカウントを借りていない可能性があります。", ephemeral=True)

# アカウントを利用するコマンド
@bot.tree.command(name="use_account")
async def use_account(interaction: discord.Interaction):
    user_id = str(interaction.user.id)

    # アカウントを既に借りているかどうかをチェック
    if not can_borrow_account(user_id):
        await interaction.response.send_message("既にアカウントを借りています。返却してください。", ephemeral=True)
    else:
        await interaction.response.send_message("利用するアカウントを選んでください:", view=AccountSelectView(user_id), ephemeral=True)

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

# Bot実行
try:
    bot.run(os.environ['TOKEN'])  # 環境変数からボットのトークンを取得
except Exception as e:
    print(f"エラーが発生しました: {e}")
    os.system("kill 1")  # ボットが停止する場合、Replit環境を終了させる
