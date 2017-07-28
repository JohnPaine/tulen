from collections import namedtuple, defaultdict
import json
import random


Card = namedtuple("Card", ["rank", "suit"])
pictured_ranks = [u"валет", u"дама", u"король", u"туз"]


class Deck:
    ranks = [str(n) for n in range(2, 11)] + pictured_ranks
    suits = u"пикей червей бубей крестей".split()

    def __init__(self):
        self._cards = []

    def __len__(self):
        return len(self._cards)

    def __getitem__(self, item):
        return self._cards[item]

    def serialize(self):
        data = []
        for card in self._cards:
            data.append(card._asdict())
        return data

    def deserialize(self, card_str_list):
        self._cards = []
        for card_str in card_str_list:
            self._cards.append(json.loads(card_str,
                                          object_hook=lambda d: namedtuple('Card', d.keys())(*d.values())))

    def append_card(self, card):
        self._cards.append(card)

    def shuffle(self):
        random.shuffle(self._cards)

    def refill(self):
        self._cards = [Card(rank, suit) for suit in self.suits for rank in self.ranks]
        self.shuffle()

    def pop(self, index=0):
        return self._cards.pop(index)

    @staticmethod
    def card_cost(card, player_score):
        if card.rank not in pictured_ranks:
            return int(card.rank)
        if card.rank in [u"король", u"валет", u"дама"]:
            return 10
        if card.rank == u"туз":
            if player_score > 21:
                return 1
            else:
                return 11