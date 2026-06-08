import discord
from typing import Optional, Dict, List, Set

class WerewolfGame:
    """人狼ゲームの状態を管理するクラス"""
    
    def __init__(self):
        """ゲーム状態を初期化"""
        self.is_playing: bool = False
        self.players: List[discord.Member] = []            
        self.roles: Dict[discord.Member, object] = {}              
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
            "人狼": 1, "占い師": 1, "怪盗": 1, "村人": 1, 
            "狂人": 0, "霊媒師": 0, "狩人": 0, "シリアルキラー": 0
        }
        self.actions: Dict[discord.Member, Dict] = {}
        self.last_executed: Optional[discord.Member] = None
        self.last_executed_role_name: Optional[str] = None
        self.thief_action_done: bool = False
        self.recruit_message: Optional[discord.Message] = None
        self.host: Optional[discord.Member] = None
        
        # アイテムシステム関連
        self.player_items: Dict[int, str] = {}  # {ユーザーid: "アイテム名"}
        self.silenced_players: Set[int] = set()  # 沈黙の御札でミュートされるプレイヤーID

    def check_victory(self) -> Optional[str]:
        """
        勝利条件をチェックする
        
        Returns:
            Optional[str]: 勝利した陣営の文字列、まだ勝利条件が満たされていない場合はNone
        """
        if not self.alive_players: return None
        
        # チーム名（role.team）ではなく、役職名（role.name）で生存者を正確に数える
        alive_role_names = []
        for p in self.alive_players:
            if p not in self.roles:
                print(f"⚠️ 警告: {p.display_name} が roles に存在しません")
                continue
            alive_role_names.append(self.roles[p].name)
        
        wolf_count = alive_role_names.count("人狼")
        sk_count = alive_role_names.count("シリアルキラー")
        
        # 狂人、村人、占い師、霊媒師、狩人、怪盗（人狼とSK以外）はすべて人間としてカウント
        human_count = len(self.alive_players) - wolf_count - sk_count
        
        # 1. シリアルキラーの勝利判定
        if sk_count > 0 and len(self.alive_players) <= 2: 
            return "シリアルキラーの勝利"
            
        # 2. 人狼陣営の勝利判定 (人狼の数が人間＋SKの合計以上になったら勝利)
        if wolf_count >= (human_count + sk_count): 
            return "人狼陣営の勝利"
            
        # 3. 村人陣営の勝利判定 (人狼とシリアルキラーが全滅したら勝利)
        if wolf_count == 0 and sk_count == 0: 
            return "村人陣営の勝利"
            
        return None

game = WerewolfGame()
