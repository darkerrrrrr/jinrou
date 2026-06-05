# roles/seer.py
import discord
from roles.base import BaseRole

class Seer(BaseRole):
    name = "占い師"
    team = "村人"
    has_night_action = True

    async def send_night_menu(self, alive_players):
        from views import RoleActionView
        # 自分以外の生存者を占う対象にする
        targets = [p for p in alive_players if p != self.player]
        
        view = RoleActionView(actor=self.player, targets=targets, placeholder="占う相手を1人選んでください", action_type="fortune")
        await self.player.send(
            f"🔮【占い師の夜行動】\n"
            f"今夜占いたいプレイヤーを下のセレクトメニューから1人選んでください。\n"
            f"結果はその場で即時開示されます。",
            view=view
        )