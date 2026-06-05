# roles/medium.py
import discord
from roles.base import BaseRole

class Medium(BaseRole):
    name = "霊媒師"
    team = "村人"
    has_night_action = False  # 夜に選ぶ行動はないためFalse

    async def send_medium_result(self, executed_member, executed_role_name):
        """朝フェーズの最初にGameCogから呼び出され、前日処刑された人の陣営をDMに通知する"""
        result = "人狼" if executed_role_name == "人狼" else "人間"
        try:
            await self.player.send(
                f"🪞【霊媒師の霊視報告】\n"
                f"昨日処刑された 【{executed_member.display_name}】 さんの霊魂を呼び出しました。\n"
                f"霊視結果: その身に宿していたのは【{result}】の魂でした。"
            )
        except discord.Forbidden:
            pass