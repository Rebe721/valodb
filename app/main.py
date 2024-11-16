async def register(interaction: discord.Interaction, name: str, account_id: str, password: str, rank: str):
    # データベースに新しいアカウントを追加
    conn = sqlite3.connect('accounts.db')
    c = conn.cursor()
    c.execute("INSERT INTO accounts (name, id, password, rank, status, borrower) VALUES (?, ?, ?, ?, 'available', '')", 
              (name, account_id, password, rank))
    conn.commit()
    conn.close()

    # ephemeralをTrueに設定して本人にのみ通知
    await interaction.response.send_message(f"アカウント **{name}** が正常に登録されました。", ephemeral=True)

# アカウントを返却するコマンド
@bot.tree.command(name="return_account")
async def return_account(interaction: discord.Interaction, name: str, new_rank: str):
    user_id = str(interaction.user.id)

    # データベースで該当アカウントを確認し、借りたアカウントであるかをチェック
    conn = sqlite3.connect('accounts.db')
    c = conn.cursor()
    c.execute("SELECT borrower FROM accounts WHERE name=? AND borrower=?", (name, user_id))
    account = c.fetchone()

    if account:
        # アカウントのランクを更新し、状態を利用可能に設定
        c.execute("UPDATE accounts SET rank=?, status='available', borrower='' WHERE name=?", (new_rank, name))
        conn.commit()
        conn.close()
        await interaction.response.send_message(f"アカウント **{name}** が返却され、ランクが更新されました。", ephemeral=True)
    else:
        conn.close()
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

# データベース初期化
init_db()

# Replitのサーバーを保持する
keep_alive()

# Botを実行（トークンを環境変数から取得）
try:
    bot.run(os.environ['TOKEN'])  # 環境変数からボットのトークンを取得
except Exception as e:
    print(f"エラーが発生しました: {e}")
    os.system("kill 1")  # ボットが停止する場合、Replit環境を終了させる
