# roles/serial_killer.py
import discord
from roles.base import BaseRole

class SerialKiller(BaseRole):
    name = "シリアルキラー"
    team = "シリアルキラー"  # 独立した第三陣営
    has_night_action = True

    async def send_night_menu(self, alive_players):
        from views import RoleActionView
        # 自分以外の生存者を殺害対象にする
        targets = [p for p in alive_players if p != self.player]
        
        view = RoleActionView(actor=self.player, targets=targets, placeholder="殺害する相手を1人選んでください", action_type="default")
        await self.player.send(
            f"🔪【シリアルキラーの夜行動】\n"
            f"今夜あなたが手にかける犠牲者を1人選んでください。\n"
            f"※人狼の襲撃よりも優先されて処理されます。",
            view=view
        )