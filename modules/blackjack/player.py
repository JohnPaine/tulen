from .deck import *


class Player:
    def __init__(self, user_id, money=0):
        self.user_id = user_id
        self.money = money
        self.bets = []
        self.stack = Deck()

    def serialize(self):
        return {
            "user_id": self.user_id,
            "money": self.money,
            "bets": self.bets,
            "stack": self.stack.serialize()
        }

    def deserialize(self, data):
        self.user_id = data["user_id"]
        self.money = data["money"]
        self.bets = data["bets"]
        self.stack.deserialize(data["stack"])

