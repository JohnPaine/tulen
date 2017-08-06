from .game_context import *


PATH_TO_CONTEXT = "./files/blackjack_{}/game_context_for_id_{}"
CONFIG_FILE = "conf.yaml"


REACT_ON_cmd = u"тюлень, хотим в блэкджек"
DEPOSIT_REQUEST_cmd = u"мой депозит"
TAKE_CARD_cmd = u"карту"
HOLD_cmd = u"хватит"
BET_ON_cmd = u"ставлю на"


class GameManager:
    def __init__(self):
        pass

    def __call__(self, message, uid, chat_id):
        if not uid:
            uid = message["user_id"]

        # self.uid = uid
        # self.chat_id = chat_id
        # self.load()
        #
        # team_name = self.get_team_name()
        # op_team_name = self.get_opponent_name(team_name)
        # op_cap_uid = self.get_team_cap_uid(op_team_name)
        # self.game_context = GameContext(uid, self.max_score, self.directory, self.is_bot_game(), team_name, uid,
        #                                 op_team_name, op_cap_uid)
        # if team_name and not self.game_context.this_team:
        #     self.game_context.this_team = self.game_context.create_team(team_name, self.uid)
        #
        # if self.check_winner():
        #     self.stop_game_session()

        return self

    def __enter__(self):
        pass
        # self.lock.acquire()

    def __exit__(self, _type, _value, _traceback):
        pass
        # self.process_bot_turn()
        # if self.check_winner():
        #     self.stop_game_session()
        # self.save()
        # self.game_context.save()
        # self.lock.release()

    def on_start_game_message(self, message):
        pass

    def on_deposit_info_message(self, message):
        pass


    @staticmethod
    def get_id(user_id, chat_id):
        if not chat_id:
            return user_id
        return -1 * chat_id

    def take_cards(self, player):
        # TODO: maybe we should refill the stack after the third of cards is gone??
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