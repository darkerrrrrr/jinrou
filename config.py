import discord
from typing import Optional, Dict, List, Set, Any, TYPE_CHECKING, Union
import asyncio

if TYPE_CHECKING:
    from roles.base import BaseRole

class RoleName:
    WOLF = "人狼"
    SEER = "占い師"
    THIEF = "怪盗"
    VILLAGER = "村人"
    MADMAN = "狂人"
    MEDIUM = "霊媒師"
    HUNTER = "狩人"
    SK = "シリアルキラー"

class WerewolfGame:
    """人狼ゲームの状態を管理するクラス"""
    
    def __init__(self):
        """ゲーム状態を初期化"""
        self.is_playing: bool = False
        self.players: List[discord.Member] = []            
        self.roles: Dict[discord.Member, 'BaseRole'] = {}              
        self.alive_players: List[discord.Member] = []      
        self.log_channel: Optional[discord.TextChannel] = None      
        self.dead_channel: Optional[discord.TextChannel] = None     
        self.wolf_channel: Optional[discord.TextChannel] = None     
        self.alive_vc: Optional[discord.VoiceChannel] = None         
        self.dead_vc: Optional[discord.VoiceChannel] = None          
        
        # 💡 アイテム（拡声器）の通知などを流すメインテキストチャンネルを記憶する変数
        self.text_channel: Optional[discord.TextChannel] = None

        self.discussion_time: int = 180
        self.night_time: int = 60
        self.morning_time: int = 15
        self.role_settings: Dict[str, int] = {
            RoleName.WOLF: 1, RoleName.SEER: 1, RoleName.THIEF: 1, RoleName.VILLAGER: 1, 
            RoleName.MADMAN: 0, RoleName.MEDIUM: 0, RoleName.HUNTER: 0, RoleName.SK: 0
        }
        self.actions: Dict[discord.Member, Dict] = {}
        self.last_executed: Optional[discord.Member] = None
        self.last_executed_role_name: Optional[str] = None
        self.thief_action_done: bool = False
        self.recruit_message: Optional[discord.Message] = None
        self.host: Optional[discord.Member] = None
        
        # アイテムシステム関連
        self.player_items: Dict[int, str] = {}  # {ユーザーid: "アイテム名"}
        self.will_notes: Dict[int, str] = {}    # {ユーザーid: "遺言内容"}
        self.silenced_players: Set[int] = set()  # 沈黙の御札でミュートされるプレイヤーID
        
        # 狂人の混乱効果
        self.confused_players: Set[int] = set()  # 混乱させられたプレイヤーID（投票先がランダムになる）

        # 進行制御用
        self.night_skip_event = asyncio.Event()

    def reset_state(self):
        """ゲームの状態を初期状態にリセットする"""
        self.is_playing = False
        self.players = []            
        self.roles = {}              
        self.alive_players = []
        self.actions = {}
        self.last_executed = None
        self.last_executed_role_name = None
        self.thief_action_done = False
        self.recruit_message = None
        self.host = None
        
        # アイテム・状態異常のリセット
        self.player_items.clear()
        self.will_notes.clear()
        self.silenced_players.clear()
        self.confused_players.clear()
        self.night_skip_event.clear()

    def check_night_actions_complete(self):
        """全員が夜の行動を終えたかチェックする"""
        required_count = 0
        if not self.roles: return
        
        # 必要なアクション数を計算
        for p in self.alive_players:
            role = self.roles.get(p)
            if not role:
                continue
            if getattr(role, "get_action_label", lambda: None)() or getattr(role, "name", "") == RoleName.VILLAGER:
                required_count += 1
        
        # 行動済みの村人をカウント
        done_villagers = 0
        for p in self.alive_players:
            role = self.roles.get(p)
            if role and getattr(role, "name", "") == RoleName.VILLAGER and p.id in self.player_items:
                done_villagers += 1
        
        # 総アクション完了数 = 役職アクション完了数 + 村人のアイテム受取完了数
        current_count = len(self.actions) + done_villagers

        if current_count >= required_count:
            self.night_skip_event.set()

    def check_victory(self) -> Optional[str]:
        """
        勝利条件をチェックする
        
        Returns:
            Optional[str]: 勝利した陣営の文字列、まだ勝利条件が満たされていない場合はNone
        """
        if not self.is_playing or len(self.alive_players) == 0: 
            return None
        
        # 生存している役職名をリスト化
        alive_roles = [getattr(self.roles[p], "name", "") for p in self.alive_players if p in self.roles]
        
        wolf_count = alive_roles.count(RoleName.WOLF)
        sk_count = alive_roles.count(RoleName.SK)
        total_alive = len(alive_roles)
        
        # 狂人、村人、占い師、霊媒師、狩人、怪盗（人狼とSK以外）はすべて人間としてカウント
        human_count = total_alive - wolf_count - sk_count
        
        # 1. シリアルキラーの勝利判定
        if sk_count > 0 and total_alive <= 2: 
            return "シリアルキラーの勝利"
            
        # 2. 人狼陣営の勝利判定 (人狼の数が人間＋SKの合計以上になったら勝利)
        if wolf_count >= (human_count + sk_count): 
            return "人狼陣営の勝利"
            
        # 3. 村人陣営の勝利判定 (人狼とシリアルキラーが全滅したら勝利)
        if wolf_count == 0 and sk_count == 0: 
            return "村人陣営の勝利"
            
        return None

game = WerewolfGame()
