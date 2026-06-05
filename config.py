# config.py

class WerewolfGame:
    def __init__(self):
        self.is_playing = False
        self.players = []            # 参加者のMemberオブジェクトリスト
        self.roles = {}              # {Member: 各役職クラスのインスタンス}
        self.alive_players = []      # 生存者リスト
        self.log_channel = None      # 進行ログ用テキストチャンネル
        self.dead_channel = None     # 霊界チャット用テキストチャンネル
        
        # 時間設定（デフォルト秒数）
        self.discussion_time = 180   
        self.night_time = 60        
        self.morning_time = 15      
        
        # 役職の枚数設定（初期値）
        self.role_settings = {
            "人狼": 1,
            "占い師": 1,
            "怪盗": 1,
            "村人": 1,
            "狂人": 0,
            "霊媒師": 0,
            "狩人": 0,
            "シリアルキラー": 0
        }
        
        # 夜のアクション・進行用データ
        self.actions = {}                 # 夜の投票先 { 行動者(Member): 対象(Member) }
        self.last_executed = None         # 直近で処刑された人（霊媒師用）
        self.last_executed_role_name = None 
        self.thief_action_done = False    # 怪盗が行動を終えたか

    def check_victory(self):
        """生存者の所属陣営を基準に勝敗判定を行う"""
        alive_role_names = [self.roles[p].name for p in self.alive_players]
        alive_teams = [self.roles[p].team for p in self.alive_players]
        
        wolf_count = alive_teams.count("人狼")
        sk_count = alive_teams.count("シリアルキラー")
        human_count = alive_teams.count("村人")
        
        # 1. シリアルキラーの勝利（生存が2人以下でSKが生き残っている）
        if sk_count > 0 and len(self.alive_players) <= 2:
            return "シリアルキラー（第三陣営）の単独勝利"
        # 2. 人狼陣営の勝利（人狼の数が人間＋SKの合計以上になる）
        if wolf_count >= (human_count + sk_count):
            return "人狼陣営の勝利"
        # 3. 村人陣営の勝利（人狼とシリアルキラーが全滅する）
        if "人狼" not in alive_role_names and "シリアルキラー" not in alive_role_names:
            return "村人陣営の勝利"
            
        return None

game = WerewolfGame()