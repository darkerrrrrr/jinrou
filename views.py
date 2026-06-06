# ─── 募集・全体設定パネル ───
class RecruitView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)

    def create_recruit_embed(self):
        roles_text = "\n".join([f"・{k}: {v}枚" for k, v in game.role_settings.items() if v > 0])
        embed = discord.Embed(title="🐺 人狼ゲーム 参加者募集中！", color=discord.Color.dark_red())
        embed.add_field(name="👥 配役構成", value=roles_text if roles_text else "未設定")
        embed.add_field(name=f"🎮 参加者 ({len(game.players)}人)", value="\n".join([p.mention for p in game.players]) if game.players else "誰も参加していません。")
        return embed

    @discord.ui.button(label="参加", style=discord.ButtonStyle.green, custom_id="join_btn")
    async def join(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user not in game.players:
            game.players.append(interaction.user)
            await interaction.response.edit_message(embed=self.create_recruit_embed(), view=self)

    @discord.ui.button(label="辞退", style=discord.ButtonStyle.red, custom_id="leave_btn")
    async def leave(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user in game.players:
            game.players.remove(interaction.user)
            await interaction.response.edit_message(embed=self.create_recruit_embed(), view=self)

    @discord.ui.button(label="⏱️ 時間設定", style=discord.ButtonStyle.secondary, custom_id="settings_btn")
    async def settings(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != game.host:
            return await interaction.response.send_message("時間設定は主催者のみ可能です。", ephemeral=True)
        await interaction.response.send_modal(TimeSettingModal(parent_view=self))

    @discord.ui.button(label="👥 役職設定", style=discord.ButtonStyle.primary, custom_id="roles_btn")
    async def role_settings(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != game.host:
            return await interaction.response.send_message("役職設定は主催者のみ可能です。", ephemeral=True)
        await interaction.response.send_message("役職変更:", view=RoleSettingView(), ephemeral=True)

    @discord.ui.button(label="▶ ゲーム開始", style=discord.ButtonStyle.blurple, custom_id="start_btn")
    async def start(self, interaction: discord.Interaction, button: discord.ui.Button):
        # 主催者チェック
        if interaction.user != game.host:
            return await interaction.response.send_message("ゲーム開始は主催者のみ可能です。", ephemeral=True)
        # 人数チェック
        if len(game.players) < 3:
            return await interaction.response.send_message("3人以上で開始してください。", ephemeral=True)
        
        # ゲーム開始処理を実行
        await interaction.response.send_message("ゲームを開始します！")
        cog = interaction.client.get_cog("GameCog")
        if cog:
            await cog.execute_game_start(interaction.channel)
