import discord
from typing import Optional, Dict, List, Set, Any, TYPE_CHECKING, Union
import json, os
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
        self.data_channel: Optional[discord.TextChannel] = None      
        
        # 💡 アイテム（拡声器）の通知などを流すメインテキストチャンネルを記憶する変数
        self.text_channel: Optional[discord.TextChannel] = None

        self.discussion_time: int = 180
        self.day_count: int = 1
        self.event_log: List[str] = []
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

        # 投票システムの状態管理 (復旧用)
        self.vote_details: Dict[int, List[Any]] = {}  # {投票者ID: [ターゲットID, 票の強さ]}
        self.voted_user_ids: Set[int] = set()
        self.banned_voters: Set[int] = set()

        # 進行制御用
        self.night_skip_event = asyncio.Event()

        # 狩人の連続護衛制限用 {狩人id: 前回守ったターゲットid}
        self.last_protected: Dict[int, int] = {}

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
        self.vote_details.clear()
        self.voted_user_ids.clear()
        self.banned_voters.clear()
        self.night_skip_event.clear()
        self.day_count = 1
        self.event_log.clear()
        self.last_protected.clear()

    def check_night_actions_complete(self):
        """全員が夜の行動を終えたかチェックする"""
        required_count = 0
        if not self.roles or not self.players: return
        
        # 必要なアクション数を計算
        for p in self.alive_players:
            role = self.roles.get(p)
            if not role: continue
            if getattr(role, "get_action_label", lambda: None)() or getattr(role, "name", "") == RoleName.VILLAGER:
                required_count += 1
        
        # 行動済みの村人をカウント
        done_villagers = len([p for p in self.alive_players if getattr(self.roles.get(p), "name", "") == RoleName.VILLAGER and p.id in self.player_items])
        
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

    def to_dict(self) -> dict:
        """状態をJSON保存可能な辞書形式に変換"""
        return {
            "is_playing": self.is_playing,
            "day_count": self.day_count,
            "role_settings": self.role_settings,
            "event_log": self.event_log,
            "player_ids": [p.id for p in self.players],
            "alive_ids": [p.id for p in self.alive_players],
            "roles": {str(p.id): self.roles[p].name for p in self.roles if p in self.roles},
            "actions": {str(m.id): {"action": d["action"], "target": d["target"].id if d["target"] else None} for m, d in self.actions.items()},
            "player_items": self.player_items,
            "will_notes": self.will_notes,
            "silenced_players": list(self.silenced_players),
            "confused_players": list(self.confused_players),
            "vote_details": {str(k): v for k, v in self.vote_details.items()},
            "voted_user_ids": list(self.voted_user_ids),
            "banned_voters": list(self.banned_voters),
            "last_protected": self.last_protected,
            "thief_action_done": self.thief_action_done
        }

    async def save_state(self, guild: discord.Guild):
        """状態をファイルに保存し、さらにDiscordの隠しチャンネルにバックアップを送信する"""
        guild_id = guild.id
        os.makedirs("data", exist_ok=True)
        data_dict = self.to_dict()
        try:
            with open(f"data/game_{guild_id}.json", "w", encoding="utf-8") as f:
                json.dump(data_dict, f, ensure_ascii=False, indent=4)
            
            # Discordの隠しチャンネルにJSONファイルを送信（2000文字制限を回避するためファイル形式で送信）
            if self.data_channel:
                import io
                json_str = json.dumps(data_dict, ensure_ascii=False, indent=2)
                file = discord.File(io.StringIO(json_str), filename=f"state_{guild_id}_day{self.day_count}.json")
                await self.data_channel.send(f"🔄 **自動セーブ：{self.day_count}日目**", file=file)
        except Exception as e:
            print(f"⚠️ 保存失敗: {e}")

    def load_from_dict(self, data: dict, guild: discord.Guild):
        """辞書データから状態を復元"""
        from roles.werewolf import Werewolf
        from roles.seer import Seer
        from roles.medium import Medium
        from roles.hunter import Hunter
        from roles.thief import Thief
        from roles.madman import Madman
        from roles.serial_killer import SerialKiller
        from roles.villager import Villager

        role_map = {
            RoleName.WOLF: Werewolf, RoleName.SEER: Seer, RoleName.MEDIUM: Medium,
            RoleName.HUNTER: Hunter, RoleName.THIEF: Thief, RoleName.MADMAN: Madman,
            RoleName.SK: SerialKiller, RoleName.VILLAGER: Villager
        }

        self.is_playing = data.get("is_playing", False)
        self.day_count = data.get("day_count", 1)
        self.role_settings = data.get("role_settings", self.role_settings)
        self.event_log = data.get("event_log", [])
        self.players = [guild.get_member(uid) for uid in data.get("player_ids", []) if guild.get_member(uid)]
        self.alive_players = [guild.get_member(uid) for uid in data.get("alive_ids", []) if guild.get_member(uid)]

        # 役職の復元
        roles_data = data.get("roles", {})
        self.roles = {}
        for uid_str, role_name in roles_data.items():
            member = guild.get_member(int(uid_str))
            if member and role_name in role_map:
                self.roles[member] = role_map[role_name](member)

        # 夜のアクションの復元
        actions_data = data.get("actions", {})
        self.actions = {}
        for uid_str, act_data in actions_data.items():
            member = guild.get_member(int(uid_str))
            if member:
                target_id = act_data.get("target")
                self.actions[member] = {
                    "action": act_data["action"],
                    "target": guild.get_member(target_id) if target_id else None
                }

        self.player_items = data.get("player_items", {})
        self.will_notes = data.get("will_notes", {})
        self.silenced_players = set(data.get("silenced_players", []))
        self.confused_players = set(data.get("confused_players", []))
        self.vote_details = {int(k): v for k, v in data.get("vote_details", {}).items()}
        self.voted_user_ids = set(data.get("voted_user_ids", []))
        self.banned_voters = set(data.get("banned_voters", []))
        self.last_protected = {int(k): v for k, v in data.get("last_protected", {}).items()}
        self.thief_action_done = data.get("thief_action_done", False)

_guild_games: Dict[int, WerewolfGame] = {}

def get_game(guild_id: int) -> WerewolfGame:
    """ギルドIDに基づいてゲームインスタンスを取得する"""
    if guild_id not in _guild_games:
        _guild_games[guild_id] = WerewolfGame()
    return _guild_games[guild_id]

def update_leaderboard(guild_id: int, winner_ids: List[int], all_player_ids: List[int], survivor_ids: List[int], team_name: str):
    """勝利したプレイヤーの統計を更新する"""
    stats_path = f"data/stats_{guild_id}.json"
    stats = {}
    if os.path.exists(stats_path):
        try:
            with open(stats_path, "r", encoding="utf-8") as f:
                stats = json.load(f)
        except: stats = {}

    # 全参加者の基本データを更新
    for uid in all_player_ids:
        uid_str = str(uid)
        # 既存データがない場合は初期化
        if uid_str not in stats:
            stats[uid_str] = {"total": 0, "human_win": 0, "wolf_win": 0, "sk_win": 0, "survived_count": 0}
        
        user_stats = stats[uid_str]
        user_stats["total"] += 1 # 参加回数

        # 勝利記録
        if uid in winner_ids:
            if team_name == "人狼": user_stats["wolf_win"] += 1
            elif team_name == "村人": user_stats["human_win"] += 1
            elif team_name == "シリアルキラー": user_stats["sk_win"] += 1
        
        # 生存記録
        if uid in survivor_ids:
            user_stats["survived_count"] += 1
            
        stats[uid_str] = user_stats

    os.makedirs("data", exist_ok=True)
    with open(stats_path, "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=4)

def get_leaderboard(guild_id: int) -> Dict[str, Any]:
    """ランキングデータを取得する"""
    stats_path = f"data/stats_{guild_id}.json"
    if not os.path.exists(stats_path): return {}
    with open(stats_path, "r", encoding="utf-8") as f:
        return json.load(f)
