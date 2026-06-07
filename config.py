import discord

class WerewolfGame:
    def __init__(self):
        self.is_playing = False
        self.players = []            
        self.roles = {}              
        self.alive_players = []      
        self.log_channel = None      
        self.dead_channel = None     
        self.wolf_channel = None     
        self.alive_vc = None         
        self.dead_vc = None          
        self.discussion_time = 180
        self.night_time = 60
        self.morning_time = 15
        self.role_settings = {
            "人狼": 1, "占い師": 1, "怪盗": 1, "村人": 1, 
            "狂人": 0, "霊媒師": 0, "狩人": 0, "シリアルキラー": 0
        }
        self.actions = {}
        self.last_executed = None
        self.last_executed_role_name = None
        self.thief_action_done = False
        self.recruit_message = None
        self.host = None

    def check_victory(self):
        if not self.alive_players: return None
        
        # チーム名（role.team）ではなく、役職名（role.name）で生存者を正確に数える
        alive_role_names = [self.roles[p].name for p in self.alive_players]
        
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
