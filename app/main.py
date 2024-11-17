import discord
from discord.ext import commands
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import os
from keep_alive import keep_alive  # keep_alive.pyをインポート

# Botの設定
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# Google Sheets 認証
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
credentials = ServiceAccountCredentials.from_json_keyfile_name("CREDENTIALS_JSON", scope)
gc = gspread.authorize(credentials)

# スプレッドシートの選択
spreadsheet = gc.open_by_key("1_xEKOwz4WsYv7C4bQRpwuRl4AOJnokFZktVpB9yIRCc")
sheet = spreadsheet.get_worksheet(0)

# Botが準備完了したときのイベント
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
        # 'borrower' カラムが存在する場合のみ比較する
        if record.get("borrower", "") == str(user_id):
            return False
    return True

# プルダウンメニューを含むView
class AccountSelectView(discord.ui.View):
    def __init__(self, user_id):
        super().__init__(timeout=None)

        # アカウントを借りている場合、メニューを表示せず通知を出す
        if not can_borrow_account(user_id):
            self.add_item(discord.ui.Button(label="すでにアカウントを借りています。", disabled=True))
            return

        # スプレッドシートから利用可能なアカウントを取得し、プルダウンメニューとして設定
        available_accounts = []
        records = sheet.get_all_records()
        for record in records:
            if record.get("status") == "available":
                available_accounts.append((record["name"], record["rank"]))

        # 名前の順序を指定通りに並べる（英字の後に続く数字でソート）
        sorted_accounts = sorted(available_accounts, key=lambda account: (account[0][0].lower(), int(''.join(filter(str.isdigit, account[0])) or 0)), reverse=True)

        # プルダウンメニューの設定
        self.account_selection = discord.ui.Select(
            placeholder="利用するアカウントを選んでください",
            options=[discord.SelectOption(label=f"{account[0]} - {account[1]}", value=account[0]) for account in sorted_accounts]
        )
        self.account_selection.callback = self.on_select_account
        self.add_item(self.account_selection)

    async def on_select_account(self, interaction: discord.Interaction):
        selected_account_name = self.account_selection.values[0]

        # スプレッドシートから選択されたアカウントの詳細情報を取得
        records = sheet.get_all_records()
        account_details = None
        for record in records:
            if record["name"] == selected_account_name:
                account_details = record
                break

        # 選択されたアカウントを借りたユーザーとして更新
        for record in records:
            if record["name"] == selected_account_name:
                record["status"] = "borrowed"
                record["borrower"] = str(interaction.user.id)
                break
        sheet.update([record.values() for record in records])  # 更新を反映

        # 選択されたアカウントの詳細情報を返す
        if account_details:
            await interaction.response.send_message(
                f"選択されたアカウントの詳細:\n"
                f"**名前**: {account_details['name']}\n"
                f"**ID**: {account_details['id']}\n"
                f"**パスワード**: {account_details['password']}\n"
                f"**ランク**: {account_details['rank']}",
                ephemeral=True
            )
        else:
            await interaction.response.send_message("アカウント情報の取得に失敗しました。", ephemeral=True)

# アカウントを登録するコマンド
@bot.tree.command(name="register")
async def register(interaction: discord.Interaction, name: str, account_id: str, password: str, rank: str):
    # スプレッドシートに新しいアカウントを登録
    sheet.append_row([name, account_id, password, rank, "available", ""])  # borrower を空白に設定
    await interaction.response.send_message(f"アカウント **{name}** が正常に登録されました。", ephemeral=True)

# アカウントを返却するコマンド
@bot.tree.command(name="return_account")
async def return_account(interaction: discord.Interaction, name: str, new_rank: str):
    user_id = str(interaction.user.id)

    # スプレッドシートで該当アカウントを確認し、借りたアカウントであるかをチェック
    records = sheet.get_all_records()
    account = None
    for record in records:
        if record["name"] == name and record.get("borrower") == user_id:
            account = record
            break

    if account:
        # アカウントのランクを更新し、状態を利用可能に設定
        account["rank"] = new_rank
        account["status"] = "available"
        account["borrower"] = ""
        sheet.update([record.values() for record in records])  # 更新を反映
        
        # 返却メッセージの送信
        await interaction.response.send_message(
            f"{interaction.user.name} が **{name}** を返却しました！ランクは **{new_rank}** に更新されました。",
            ephemeral=True
        )
    else:
        await interaction.response.send_message("アカウントの返却に失敗しました。指定されたアカウントを借りていない可能性があります。", ephemeral=True)

# スラッシュコマンド: アカウント利用
@bot.tree.command(name="use_account")
async def use_account(interaction: discord.Interaction):
    user_id = str(interaction.user.id)

    # アカウントを既に借りているかどうかをチェック
    if not can_borrow_account(user_id):
        await interaction.response.send_message("既にアカウントを借りています。返却してください。", ephemeral=True)
    else:
        await interaction.response.send_message("利用するアカウントを選んでください:", view=AccountSelectView(user_id), ephemeral=True)

# スラッシュコマンド: ヘルプ
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

# Replitのサーバーを保持する
keep_alive()

# Botを実行（トークンを環境変数から取得）
try:
    bot.run(os.environ['TOKEN'])  # 環境変数からボットのトークンを取得
except Exception as e:
    print(f"エラーが発生しました: {e}")
    os.system("kill 1")  # ボットが停止する場合、Replit環境を終了させる
