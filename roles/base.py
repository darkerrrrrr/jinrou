class BaseRole:
    def __init__(self, player=None):
        self.player = player
    name = "平民"
    team = "村人"
    
    def get_action_label(self):
        return None
