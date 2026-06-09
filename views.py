import discord
from config import get_game, RoleName, RoleLiteral
from discord.ext import commands
from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from cogs.game import GameCog

class RecruitView(discord.ui.View):
    def __init__(self): 
        super().__init__(timeout=None)

    def create_recruit_embed(self, guild_id: int):
        game = get_game(guild_id)
        roles_text = "\n".join([f"・{k}: {v}枚" for k, v in game.role_settings.items() if v > 0])
        embed = discord.Embed(title="🐺 人狼ゲーム", color=discord.Color.dark_red())
        
        embed.add_field(name="👥 配役構成", value=roles_text if roles_text else "未設定")
        embed.add_field(name=f"🎮 参加者 ({len(game.players)}人)", value="\n".join([p.mention for p in game.players]) if game.players else "誰も参加していません。")
        return embed

    @discord.ui.button(label="参加", style=discord.ButtonStyle.green, custom_id="join_btn")
    async def join(self, interaction: discord.Interaction, button: discord.ui.Button):
        game = get_game(interaction.guild.id)
        if interaction.user not in game.players:
            game.players.append(interaction.user)
            await interaction.response.edit_message(embed=self.create_recruit_embed(interaction.guild.id), view=self)

    @discord.ui.button(label="辞退", style=discord.ButtonStyle.red, custom_id="leave_btn")
    async def leave(self, interaction: discord.Interaction, button: discord.ui.Button):
        game = get_game(interaction.guild.id)
        if interaction.user in game.players:
            game.players.remove(interaction.user)
            await interaction.response.edit_message(embed=self.create_recruit_embed(interaction.guild.id), view=self)

    @discord.ui.button(label="⏱️ 時間設定", style=discord.ButtonStyle.secondary, custom_id="settings_btn")
    async def settings(self, interaction: discord.Interaction, button: discord.ui.Button):
        game = get_game(interaction.guild.id)
        if not game.host or interaction.user.id != game.host.id: 
            return await interaction.response.send_message("主催者のみ可能です。", ephemeral=True)
        await interaction.response.send_modal(TimeSettingModal(parent_view=self))

    @discord.ui.button(label="👥 役職設定", style=discord.ButtonStyle.primary, custom_id="roles_btn")
    async def role_settings(self, interaction: discord.Interaction, button: discord.ui.Button):
        game = get_game(interaction.guild.id)
        if not game.host or interaction.user.id != game.host.id: 
            return await interaction.response.send_message("主催者のみ可能です。", ephemeral=True)
        await interaction.response.send_message("役職変更:", view=RoleSettingView(interaction.guild.id), ephemeral=True)

    @discord.ui.button(label="▶ ゲーム開始", style=discord.ButtonStyle.blurple, custom_id="start_btn")
    async def start(self, interaction: discord.Interaction, button: discord.ui.Button):
        game = get_game(interaction.guild.id)
        if not game.host or interaction.user.id != game.host.id: 
            return await interaction.response.send_message("主催者のみ可能です。", ephemeral=True)
        # テストプレイ用に1人以上で開始可能に変更
        if len(game.players) < 1: return await interaction.response.send_message("参加者がいないため開始できません。", ephemeral=True)
        
        channel = interaction.channel
        if not isinstance(channel, (discord.TextChannel, discord.Thread)):
            return await interaction.response.send_message("エラー: チャンネル情報を取得できませんでした。", ephemeral=True)

        await interaction.response.send_message("ゲームを開始します！")
        
        bot = cast(commands.Bot, interaction.client)
        cog = bot.get_cog("GameCog")
        if cog:
            # 動的な代入のため getattr を使用しつつ、エラーを抑止
            func = getattr(cog, "execute_game_start", None)
            if func:
                await func(channel)

class TimeSettingModal(discord.ui.Modal):
    discussion_input = discord.ui.TextInput(label='昼の議論時間 (秒)', default='180', max_length=4)
    night_input = discord.ui.TextInput(label='夜の行動時間 (秒)', default='60', max_length=4)
    morning_input = discord.ui.TextInput(label='朝の結果発表時間 (秒)', default='15', max_length=4)
    def __init__(self, parent_view):
        super().__init__(title='ゲーム時間の設定')
        self.parent_view = parent_view
    async def on_submit(self, interaction: discord.Interaction):
        try:
            game = get_game(interaction.guild.id)
            discussion_time = int(self.discussion_input.value)
            night_time = int(self.night_input.value)
            morning_time = int(self.morning_input.value)
            
            # バリデーション：正の数のみ許可
            if discussion_time <= 0 or night_time <= 0 or morning_time <= 0:
                return await interaction.response.send_message("⚠️ 時間は1秒以上で設定してください。", ephemeral=True)
            if discussion_time > 3600 or night_time > 3600 or morning_time > 3600:
                return await interaction.response.send_message("⚠️ 時間は3600秒以下で設定してください。", ephemeral=True)
            
            game.discussion_time = discussion_time
            game.night_time = night_time
            game.morning_time = morning_time
            
            if game.recruit_message: 
                await game.recruit_message.edit(embed=self.parent_view.create_recruit_embed(interaction.guild.id), view=self.parent_view)
            await interaction.response.send_message("✅ 更新しました。", ephemeral=True)
        except ValueError:
            await interaction.response.send_message("⚠️ 時間は数字で入力してください。", ephemeral=True)

class RoleCountSelect(discord.ui.Select):
    def __init__(self, guild_id: int, selected_role: RoleLiteral):
        self.selected_role: RoleLiteral = selected_role
        game = get_game(guild_id)
        current = game.role_settings[selected_role]
        limited = [RoleName.SK, RoleName.THIEF, RoleName.SEER, RoleName.HUNTER, RoleName.MADMAN, RoleName.MEDIUM]
        limit = 2 if selected_role in limited else 4
        # 0枚から始める（役職なしも選択可能）
        options = [discord.SelectOption(label=f"{i}枚", value=str(i), default=(current == i)) for i in range(0, limit + 1)]
        super().__init__(placeholder=f"【{selected_role}】の枚数を選択", options=options)

    async def callback(self, interaction: discord.Interaction):
        game = get_game(interaction.guild.id)
        game.role_settings[self.selected_role] = int(self.values[0])
        if game.recruit_message: await game.recruit_message.edit(embed=RecruitView().create_recruit_embed(interaction.guild.id), view=RecruitView())
        await interaction.response.edit_message(content="更新しました。", view=RoleSettingView(interaction.guild.id))

class RoleSelectMenu(discord.ui.Select):
    def __init__(self, guild_id: int):
        game = get_game(guild_id)
        options = [discord.SelectOption(label=f"{r} ({game.role_settings[r]}枚)", value=r) for r in game.role_settings.keys()]
        super().__init__(placeholder="変更したい役職を選択...", options=options)
    async def callback(self, interaction: discord.Interaction):
        v = discord.ui.View()
        v.add_item(RoleCountSelect(interaction.guild.id, cast(RoleLiteral, self.values[0])))
        await interaction.response.edit_message(content="枚数を選択:", view=v)

class RoleSettingView(discord.ui.View):
    def __init__(self, guild_id: int):
        super().__init__(timeout=60)
        self.add_item(RoleSelectMenu(guild_id))
        close_btn = discord.ui.Button(label="設定完了", style=discord.ButtonStyle.secondary)
        async def close_callback(interaction: discord.Interaction): await interaction.response.edit_message(content="完了しました。", view=None)
        close_btn.callback = close_callback
        self.add_item(close_btn)