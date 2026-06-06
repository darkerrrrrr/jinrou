import discord

class WerewolfGame:
    def __init__(self):
        self.is_playing = False
        self.players = []            
        self.roles = {}              
        self.alive_players = []      
        # チャンネル管理用
        self.log_channel = None      
        self.dead_channel = None     
        self.wolf_channel = None     
        
        # 時間設定
        self.discussion_time = 180
        self.night_time = 60
        self.morning_time = 15
        
        # 役職設定
        self.role_settings = {
            "人狼": 1, "占い師": 1, "怪盗": 1, "村人": 1, 
            "狂人": 0, "霊媒師": 0, "狩人": 0, "シリアルキラー": 0
        }
        
        # ゲーム進行用フラグとデータ
        self.actions = {}
        self.last_executed = None
        self.last_executed_role_name = None
        self.thief_action_done = False

    def check_victory(self):
        # alive_playersが空の場合は判定しない
        if not self.alive_players: return None
        
        alive_role_names = [self.roles[p].name for p in self.alive_players]
        alive_teams = [self.roles[p].team for p in self.alive_players]
        
        wolf_count = alive_teams.count("人狼")
        sk_count = alive_teams.count("シリアルキラー")
        human_count = alive_teams.count("村人")
        
        if sk_count > 0 and len(self.alive_players) <= 2:
            return "第三陣営の勝利"
        if wolf_count >= (human_count + sk_count):
            return "人狼陣営の勝利"
        if "人狼" not in alive_role_names and "シリアルキラー" not in alive_role_names:
            return "村人陣営の勝利"
            
        return None

game = WerewolfGame()
