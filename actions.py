import discord
from config import get_game, RoleName
from typing import Optional, List, Union

class ActionSelect(discord.ui.Select):
    def __init__(self, actor: discord.Member, action_label: str):
        self.actor: discord.Member = actor
        self.action_label: str = action_label
        
        # インスタンス生成時にギルドのゲーム状態を取得
        game = get_game(actor.guild.id)
        
        # 狩人の場合、前回守ったターゲットを除外する
        last_id = game.last_protected.get(actor.id)
        is_hunter = (game.roles.get(actor) and game.roles[actor].name == RoleName.HUNTER)

        # テストプレイ用に、自分以外がいない場合は自分を選択肢に入れる（メニューが空になるのを防ぐ）
        valid_targets = [p for p in game.alive_players if p != actor]
        if not valid_targets: valid_targets = game.alive_players

        options = [
            discord.SelectOption(label=p.display_name, value=str(p.id)) 
            for p in valid_targets if not is_hunter or p.id != last_id
        ]
        super().__init__(placeholder="対象のプレイヤーを選択...", options=options)

    async def callback(self, interaction: discord.Interaction):
        target_id = int(self.values[0])
        guild = interaction.guild
        if not guild:
            return await interaction.response.send_message("このコマンドはサーバー内でのみ有効です。", ephemeral=True)
        game = get_game(guild.id)

        # メンバーの取得
        target_user: Optional[Union[discord.Member, discord.User]] = guild.get_member(target_id)
        if target_user is None:
            try: target_user = await guild.fetch_member(target_id)
            except: pass
        
        # ここで「discord.Member」であることを厳密にチェック
        if not isinstance(target_user, discord.Member):
            return await interaction.response.send_message("ターゲットが見つかりません。", ephemeral=True)
        
        # 既にゲームから除外されているかチェック
        if target_user not in game.alive_players:
             return await interaction.response.send_message("そのプレイヤーは既に生存していません。", ephemeral=True)

        game.actions[self.actor] = {"action": self.action_label, "target": target_user}
        game.check_night_actions_complete()
        await interaction.response.edit_message(content=f"選択完了: 【{target_user.display_name}】に「{self.action_label}」を行います。", view=None)

class ActionView(discord.ui.View):
    def __init__(self, actor: discord.Member, action_label: str, timeout: int = 60):
        super().__init__(timeout=timeout)
        self.add_item(ActionSelect(actor, action_label))
        self.message: Optional[discord.Message] = None

    async def on_timeout(self):
        for item in self.children:
            if isinstance(item, (discord.ui.Button, discord.ui.Select)):
                item.disabled = True
        if self.message:
            try:
                await self.message.edit(content="⌛ 時間切れです。行動を選択できませんでした。", view=self)
            except: pass