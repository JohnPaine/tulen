#!/usr/bin/python
# -*- coding: utf-8 -*-

from collections import namedtuple, defaultdict
import io
import json
import random
import yaml


def load_json(filename):
    try:
        data = json.load(open(filename))
    except:
        return None
    return data


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


PATH_TO_CONTEXT = "./files/blackjack_{}/game_context_for_id_{}"
CONFIG_FILE = "conf.yaml"


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


class Processor:
    def __init__(self, vk_user):
        self.exclusive = True
        self.config = yaml.load(open(vk_user.module_file("blackjack", CONFIG_FILE)))
        self.vk_user = vk_user

        self.game_context = None
        self.game_context_path = ""

    @staticmethod
    def get_id(user_id, chat_id):
        if not chat_id:
            return user_id
        return -1 * chat_id

    def take_cards(self, player):
        # TODO: maybe we should refill stack after the third of cards are gone??
        if not len(self.game_context.game_stack):
            self.game_context.game_stack.refill()

        card = self.game_context.game_stack.pop()
        player.stack.append_card(card)

        # if len(self.game_context.game_stack) > 0:
        #     card = self.game_context.game_stack.pop()
        #     self.game_context.user_stack.append(card)
        # if len(self.game_context.game_stack) > 0 and self.get_bender_scores() < 20:
        #     card = self.game_context.game_stack.pop()
        #     self.game_context.bender_stack.append(card)

    def start_new_game(self, game_id):
        self.game_context = GameContext(game_id)
        self.game_context.game_stack.refill()
        # self.user_stack = []
        # self.bender_stack = []

        # each player takes 2 cards
        self.take_cards()
        self.take_cards()

        # if not self.game_context:
        #     self.game_context = {"players": defaultdict(Player),
        #                          "bender_bets": [],
        #                          "user_bets": [],
        #                          "game_stack": self.game_stack,
        #                          "bender_stack": self.bender_stack,
        #                          "user_stack": self.user_stack,
        #                          "session_started": True}
        # else:
        #     self.game_context["bender_bets"] = []
        #     self.game_context["user_bets"] = []
        #     self.game_context["game_stack"] = self.game_stack
        #     self.game_context["bender_stack"] = self.bender_stack
        #     self.game_context["user_stack"] = self.user_stack
        #     self.game_context["session_started"] = True
        #     self.payback_users()

    def gen_win_or_loose_text(self, win):
        text = u""
        text += u"Ставки: на тюленя: {}, на вас: {}\n".format(self.total_on_bot(), self.total_on_user())
        text += u"\nу тюленя - {} очков".format(self.get_bender_scores())
        text += u"\nу вас - {} очков".format(self.get_user_scores())

        self.refund_users(win)
        self.game_context["bender_bets"] = []
        self.game_context["user_bets"] = []

        if win:
            text += u"\n Победили вы!"
        else:
            text += u"\n Победил Тюлень = ("

        return text

    def generate_message(self, finish=False):

        text = u""
        if not finish:
            text += u"Ставки: на тюленя: {}, на вас: {}\n".format(self.total_on_bot(), self.total_on_user())
            text += u"{} карт(ы) у тюленя\n".format(len(self.game_context.bender_stack))
            text += u"{} карт(ы) у вас: ".format(len(self.game_context.user_stack))

            user_score = self.get_user_scores()
            card_text = []
            for card in self.game_context.user_stack:
                card_text.append(u"{} {}".format(card.rank, card.suit))
            text += ", ".join(card_text)
            text += "\n"
            text += u"Очков: {}".format(user_score)

        if self.get_user_scores() >= 21:
            finish = True

        if finish:
            self.game_context["session_started"] = False
            if self.get_user_scores() == 21:
                return text + self.gen_win_or_loose_text(True)

            if self.get_user_scores() > 21:
                return text + self.gen_win_or_loose_text(False)
            if self.get_bender_scores() > 21:
                return text + self.gen_win_or_loose_text(True)
            if self.get_user_scores() > self.get_bender_scores():
                return text + self.gen_win_or_loose_text(True)
            else:
                return self.gen_win_or_loose_text(False)

        return text

    @staticmethod
    def get_scores(stack):
        score = 0
        for card in stack:
            score += Deck.card_cost(card, score)
        result_score = 0
        for card in stack:
            result_score += Deck.card_cost(card, score)
        return result_score

    def get_user_scores(self):
        return self.get_scores(self.game_context.user_stack)

    def get_bender_scores(self):
        return self.get_scores(self.game_context.bender_stack)

    def save_context(self):
        with io.open(self.game_context_path, 'w', encoding='utf-8') as f:
            f.write(str(json.dumps(self.game_context, ensure_ascii=False, indent=4, separators=(',', ': '))))

    def process_bet_on_user(self, uid, bet):
        if not self.player_exists(uid):
            self.add_money(5000, uid)

        if self.get_money(uid) < bet:
            bet = self.get_money(uid)
        if bet == 0:
            return u"Да вы банкрот, батенька, пиздуйте из казино."

        self.bet_on_user(bet, uid)
        self.take_money(bet, uid)
        return u"Ставка в размере {} рупий на нас принята".format(bet)

    def process_bet_on_bot(self, uid, bet):
        if not self.player_exists(uid):
            self.add_money(5000, uid)

        if self.get_money(uid) < bet:
            bet = self.get_money(uid)
        if bet == 0:
            return u"Да вы банкрот, батенька, пиздуйте из казино."

        self.bet_on_bot(bet, uid)
        self.take_money(bet, uid)
        return u"Ставка в размере {} рупий на бота принята".format(bet)

    def player_exists(self, uid):
        return uid in self.game_context["players"].keys()

    def get_money(self, uid):
        return self.game_context["players"][uid].money

    def add_money(self, num, uid):
        self.game_context["players"][uid].money += num

    def take_money(self, num, uid):
        self.game_context["players"][uid].money -= num

    def bet_on_bot(self, num, uid):
        self.game_context["bender_bets"].append((uid, num))

    def bet_on_user(self, num, uid):
        self.game_context["user_bets"].append((uid, num))

    def get_deposit(self, uid):
        if not self.player_exists(uid):
            self.add_money(5000, uid)

        return u"У вас на счету {}, дорогуша".format(self.get_money(uid))

    def total_on_bot(self):
        num = 0
        for bet in self.game_context["bender_bets"]:
            num += bet[1]

        return num

    def total_on_user(self):
        num = 0
        for bet in self.game_context["user_bets"]:
            num += bet[1]

        return num

    def payback_users(self):
        for it in self.game_context["bender_bets"]:
            self.add_money(it[1], it[0])

        for it in self.game_context["user_bets"]:
            self.add_money(it[1], it[0])

    def refund_users(self, we_win):
        total_user_bet = self.total_on_user()
        total_bot_bet = self.total_on_bot()
        k = 0

        if we_win:
            if total_user_bet == 0:
                k = 0
            else:
                k = float(total_bot_bet) / float(total_user_bet)

            for it in self.game_context["user_bets"]:
                self.add_money(it[1] + it[1] * k, it[0])
        else:
            if total_bot_bet == 0:
                k = 0
            else:
                k = float(total_user_bet) / float(total_bot_bet)

            for it in self.game_context["bender_bets"]:
                self.add_money(it[1] + it[1] * k, it[0])

        a = len(self.game_context["bender_bets"]) + len(self.game_context["user_bets"])
        if a == 1:
            for it in self.game_context["user_bets"]:
                self.add_money(it[1] * 0.25, it[0])
            for it in self.game_context["bender_bets"]:
                self.add_money(it[1] * 0.25, it[0])

    def try_process_bet_on_player(self, message_body, chat_id, user_id, player_id):
        bot_bet_commands = [u"ставлю на бота", u"ставлю на тюленя"]
        player_bet_commands = [u"ставлю на нас"]
        bet_commands = bot_bet_commands + player_bet_commands

        for bet_cmd in bet_commands:
            if bet_cmd not in message_body:
                continue

            try:
                bet = int(message_body[len(bet_cmd):])
            except Exception as e:
                print("blackjack: bet placement was invalid, message_body: {}, e: {}".format(message_body, e))
                bet = None
            if not bet:
                self.vk_user.send_message(u"я таки не понял, что вы ставите?", chatid=chat_id, userid=user_id)
                return True

            if bet_cmd in bot_bet_commands:
                text = self.process_bet_on_bot(player_id, abs(bet))
            else:
                text = self.process_bet_on_user(player_id, abs(bet))

            self.save_context()
            self.vk_user.send_message(text, chatid=chat_id, userid=user_id)

            return True
        return False

    def load_game_context(self, user_id, chat_id):
        game_id = self.get_id(user_id, chat_id)

        self.game_context_path = PATH_TO_CONTEXT.format(self.vk_user.user_id, game_id)
        self.game_context = load_json(self.game_context_path)

    def process_message(self, message, chat_id, user_id):

        message_body = message["body"].lower().strip()
        self.load_game_context(user_id, chat_id)
        # in chat game user_id would be empty, but not in the message
        player_id = message["user_id"]

        if message_body.startswith(self.config["react_on"]):
            self.start_new_game(self.get_id(user_id, chat_id))
            self.save_context()
            self.vk_user.send_message(text=self.generate_message(), chatid=chat_id, userid=user_id)
            return True

        if message_body.startswith(u"мой депозит"):
            self.save_context()
            self.vk_user.send_message(self.get_deposit(player_id), chatid=chat_id, userid=user_id)
            return True

        if not self.game_context["session_started"]:
            return False

        if message_body.startswith(u"карту"):
            for i in self.game_context["bender_bets"]:
                if message["user_id"] == i[0]:
                    self.vk_user.send_message(u"Вы поставили на тюленя, не мешайте игре", chatid=chat_id, userid=user_id)
                    return True

            self.take_cards()
            text = self.generate_message()
            self.save_context()
            self.vk_user.send_message(text=text, chatid=chat_id, userid=user_id)
            return True

        if message_body.startswith(u"хватит"):
            for i in self.game_context["bender_bets"]:
                if message["user_id"] == i[0]:
                    self.vk_user.send_message(u"Вы поставили на тюленя, не мешайте игре", chatid=chat_id, userid=user_id)
                    return True

            text = self.generate_message(finish=True)
            self.save_context()

            self.vk_user.send_message(text, chatid=chat_id, userid=user_id)
            return True

        return self.try_process_bet_on_player(message_body, chat_id, user_id, message["user_id"])
