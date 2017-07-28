from .player import *


class GameContext:
    def __init__(self, game_id):
        self.game_id = game_id
        self.game_stack = Deck()
        self.game_stack.refill()
        self.players = {"bender": Player("bender")}

    def serialize(self):
        return {
            "game_id": self.game_id,
            "game_stack": self.game_stack.serialize()
        }

    def deserialize(self, data):
        self.game_id = data["game_id"]
        self.game_stack.deserialize(data["game_stack"])