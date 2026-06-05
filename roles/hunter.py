# roles/hunter.py
import discord
from roles.base import BaseRole

class Hunter(BaseRole):
    name = "狩人"
    team = "村人"
    has_night_action = True

    async def send_night_menu(self, alive_players):
        from views import RoleActionView
        # 自分以外の生存者を守る対象にする
        targets = [p for p in alive_players if p != self.player]
        
        view = RoleActionView(actor=self.player, targets=targets, placeholder="護衛する相手を1人選んでください", action_type="default")
        await self.player.send(
            f"🏹【狩人の夜行動】\n"
            f"今夜人狼の襲撃から守りたいプレイヤーを1人選んでください（自分は選べません）。",
            view=view
        )