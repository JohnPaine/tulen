#!/usr/bin/python
# -*- coding: utf-8 -*-

from game_context import *
from ship_processing import Point as _Point
from ship_processing import SHIP_RANKS_DICT as shipRanks
from datetime import datetime
import threading


class GameManager:
    def __init__(self, vk_user, questions, directory):
        self.lock = threading.Lock()
        self.vk_user = vk_user
        self.questions = questions
        self.directory = directory

        if not self.questions or len(self.questions) == 0:
            self.questions = map(lambda x: {x: str(x)}, range(1, 201))
        self.max_score = reduce(lambda x, y: x + y, (key * value for key, value in shipRanks.iteritems()))

        # serializable data
        self.teams = {}
        self.games = []
        self.active_sessions = []

        # local data
        self.bot_turn = False
        self.hit_was_made = False

        self.load()

    def __call__(self, message, uid, chat_id):
        if not uid:
            uid = message["user_id"]

        self.uid = uid
        self.chat_id = chat_id
        self.load()

        team_name = self.get_team_name()
        op_team_name = self.get_opponent_name(team_name)
        op_cap_uid = self.get_team_cap_uid(op_team_name)
        self.game_context = GameContext(uid, self.max_score, self.directory, self.is_bot_game(), team_name, uid, op_team_name, op_cap_uid)
        if team_name and not self.game_context.this_team:
            self.game_context.this_team = self.game_context.create_team(team_name, self.uid)

        if self.check_winner():
            self.stop_game_session()

        return self

    def __enter__(self):
        self.lock.acquire()

    def __exit__(self, type, value, traceback):
        self.process_bot_turn()
        if self.check_winner():
            self.stop_game_session()
        self.save()
        self.game_context.save()
        self.lock.release()

    #   game commands   ================================================================================================

    @need_no_game_session
    def start_game_session(self, message=""):
        self.active_sessions.append({"session_uid": self.uid,
                                     "session_started": datetime.now().strftime("%d.%m.%Y %H:%M:%S"),
                                     "questioned_game": False})
        msg = SESSION_STARTED_MSG.format(self.uid)
        msg += u"\n\nДля игры вам необходимо зарегистрировать команду, загрузить карту, " \
               u"выбрать оппонента из числа зарегистрированных команд, дождаться начала игры с ним, " \
               u"после чего начинать атаку на корабли оппонента.\n\n" \
               u"Или вы можете играть со мной в качестве оппонента, тогда вместо команды оппонента вам нужно выбрать меня." \
               u"Пример очередности ваших команд:\n" \
               u"1. я капитан команды ИМЯ_КОМАНДЫ\n" \
               u"2. загрузи карту МАССИВ_КАРТЫ\n" \
               u"Или, если хотите чтобы я сгенерил вам карту:\n" \
               u"2. загрузи рандомную карту\n" \
               u"3. играю с командой ИМЯ_КОМАНДЫ_ОППОНЕНТА\n" \
               u"Или, если хотите играть со мной:\n" \
               u"3. играю с тюленем\n" \
               u"4. атакую КООРДИНАТА_X(цифрой [1-10]),КООРДИНАТА_Y(цифрой [1-10] или буквой [a-j])\n" \
               u"И так далее, повторяя действие 4, до окончания игры.\n\n" \
               u"Чтобы покинуть игру напишите Мы закончили морской бой\n" \
               u"Список игровых команд выводится по команде Инструкция\n"
        return msg

    @need_no_game_session
    def start_questioned_game_session(self, message=""):
        self.active_sessions.append({"session_uid": self.uid,
                                     "session_started": datetime.now().strftime("%d.%m.%Y %H:%M:%S"),
                                     "questioned_game": True})
        msg = SESSION_STARTED_MSG.format(self.uid)
        msg += u"\n\nДля игры вам необходимо зарегистрировать команду, загрузить карту, " \
               u"выбрать оппонента из числа зарегистрированных команд, дождаться начала игры с ним, " \
               u"после чего начинать атаку на корабли оппонента, предварительно отвечая на вопросы игры.\n\n" \
               u"Пример очередности ваших команд:\n" \
               u"1. я капитан команды ИМЯ_КОМАНДЫ\n" \
               u"2. загрузи карту МАССИВ_КАРТЫ\n" \
               u"Или, если хотите чтобы я сгенерил вам карту:\n" \
               u"2. загрузи рандомную карту\n" \
               u"3. играю с командой ИМЯ_КОМАНДЫ_ОППОНЕНТА\n" \
               u"Или, если хотите играть со мной:\n" \
               u"3. играю с тюленем\n" \
               u"4. вопросы\n" \
               u"5. ответ НОМЕР_ВОПРОСА ОТВЕТ\n" \
               u"6. атакую КООРДИНАТА_X(цифрой [1-10]),КООРДИНАТА_Y(цифрой [1-10] или буквой [a-j])\n" \
               u"И так далее, повторяя действия 5 и 6, до окончания игры.\n\n" \
               u"Чтобы покинуть игру напишите Мы закончили морской бой\n" \
               u"Список игровых команд выводится по команде Инструкция\n"
        return msg

    @need_game_session
    @need_game_context
    @need_game_not_started
    @can_register_team
    def register_team(self, message):
        team_name = get_command_args_str(registerTeam_command, message).replace(' ', '_')

        self.teams[team_name] = {"team_uid": self.uid, "team_chat_id": self.chat_id}
        self.game_context.this_team_name = team_name
        self.game_context.this_team = self.game_context.create_team(team_name, self.uid)
        self.game_context.opponent = None
        self.game_context.op_team_name = None
        self.game_context.op_cap_uid = None
        self.game_context.bot_game = False
        GameContext.save_team_data(self.game_context.this_team, None, self.directory)

        return REGISTERED_TEAM_MSG.format(team_name, self.uid)

    @need_game_session
    def show_commands(self, message=""):
        answer = u"команды игры Морской Бой:\n"
        answer += start_game_processing_command + u"\n"
        answer += start_questioned_game_processing_command + u"\n"
        answer += registerTeam_command + u"\n"
        answer += loadMap_command + u"\n"
        answer += loadRandomMap_command + u"\n"
        answer += questions_command + u"\n"
        answer += showTeams_command + u"\n"
        answer += gameRequest_command + u"\n"
        answer += bot_gameRequest_command + u"\n"
        answer += answer_command + u"\n"
        answer += attack_command + u"\n"
        answer += showMaps_command + u"\n"
        answer += showGameCommands_command + u"\n"
        answer += stop_game_processing_command + u"\n"
        return answer

    @need_game_session
    def show_teams(self, message=""):
        answer = u"зарегистрированные команды:\n"
        for team_name in self.teams.keys():
            answer += team_name + u"\n"
        return answer

    @need_questioned_game_session
    @need_game_context
    @need_registration
    def get_questions(self, message=""):
        # return u"Воспросы смотрите у меня на стене"
        ans = u"\n"
        for i, q in enumerate(self.questions):
            a = q.keys()[0]
            if a:
                ans += u"Вопрос {}: {}\n".format(i + 1, a)

        return ans

    @need_game_session
    @need_game_context
    @need_registration
    @need_game_not_started
    def load_map(self, message):
        field = get_command_args_str(loadMap_command, message)
        return self.game_context.this_team.parse_fields(field)

    @need_game_session
    @need_game_context
    @need_registration
    @need_game_not_started
    def load_random_map(self, message):
        field = Team.generate_random_map()
        if len(field) != MAP_SIZE * MAP_SIZE:
            return field
        resp = self.game_context.this_team.parse_fields(field)
        if resp == GOOD_MAP_MSG:
            ans = u"Загрузил карту:\n"
            img_filename = self.game_context.this_team.print_fields_pic(False)

            msg_attachments = self.vk_user.upload_images_files([img_filename])
            print 'self.chat_id - ', self.chat_id
            print 'self.uid - ', self.uid
            self.send_message(message=ans, attachments=msg_attachments, chat_id=self.chat_id, uid=self.uid)
            return u"Выбирайте соперника".format(self.chat_id, self.uid)
            # return u"Загрузил карту:\n" + Team.print_fields_s(field, generate_field_of_shots(), False)
        else:
            return resp

    @need_game_session
    @need_game_context
    @need_registration
    @need_valid_map
    @need_game_not_started
    def game_request(self, message):
        try:
            op_team_name = get_command_args_str(gameRequest_command, message).replace(' ', '_')

            print("Game requested with team {}".format(op_team_name.encode('utf8')))

            if not op_team_name or op_team_name not in self.teams:
                return UNKNOWN_TEAM_MSG.format(op_team_name)

            return self.start_game_with(op_team_name)
        except Exception as e:
            print "Exception occurred while parsing opponent team name - {}".format(e.message)
            return u"Эммм, что-то пошло не так =/ Попробуйте ещё раз"

    @need_game_session
    @need_game_context
    @need_registration
    @need_valid_map
    @need_game_not_started
    def bot_game_request(self, message):
        return self.start_game_with_bot()

    @need_game_session
    @need_game_context
    @need_registration
    @need_valid_map
    def show_maps(self, message=""):
        gc = self.game_context
        ans = u"Ваше поле:\n"
        img_filename = gc.this_team.print_fields_pic(False)

        msg_attachments = self.vk_user.upload_images_files([img_filename])
        self.send_message(message=ans, attachments=msg_attachments, chat_id=self.chat_id, uid=self.uid)

        if gc.opponent:
            ans = u"Поле выстрелов по оппоненту:\n"
            img_filename = gc.opponent.print_fields_pic(True)

            msg_attachments = self.vk_user.upload_images_files([img_filename])
            self.send_message(message=ans, attachments=msg_attachments, chat_id=self.chat_id, uid=self.uid)

        return u"Ходите"

    @need_questioned_game_session
    @need_game_context
    @need_registration
    @need_valid_map
    @need_opponent_set
    @need_game_started
    def parse_answer(self, message):
        data = get_command_args_str(answer_command, message)
        try:
            ans = data.split(' ')
            if len(ans) < 2:
                return INVALID_ANSWER_FORMAT_MSG
            q_number = int(ans[0].strip())
            q_answer = ans[1].strip()
        except:
            return INVALID_ANSWER_FORMAT_MSG

        if q_number < 1 or q_number > len(self.questions):
            return INVALID_ANSWER_NUMBER_MSG

        return self.question_was_answered(q_number - 1, self.is_answer_correct(q_answer, q_number - 1))

    @need_game_session
    @need_game_context
    @need_registration
    @need_valid_map
    @need_opponent_set
    @need_game_started
    @need_question_answered
    def attack(self, message, bot_turn=False):
        gc = self.game_context

        if bot_turn:
            team = gc.this_team
            self.send_message(self.uid, self.chat_id, u"Стреляет тюлень...\n")
            hit_point = _Point(random.randint(0, MAP_SIZE - 1), random.randint(0, MAP_SIZE - 1), -1, False)
            while self.is_shot_was_made(hit_point, team) or not self.is_shot_correct(hit_point, team):
                hit_point = _Point(random.randint(0, MAP_SIZE - 1), random.randint(0, MAP_SIZE - 1), -1, False)
                print("\t\tGENERATING NEW POINT - {}!\n".format(hit_point))
        else:
            team = gc.opponent
            coords_str = get_command_args_str(attack_command, message)
            hit_point = _Point.try_parse(coords_str)

        if hit_point and not isinstance(hit_point, _Point):
            return hit_point
        if hit_point:
            result, ship = self.process_shot(hit_point, team)
            self.process_drawn_ships(result, ship, team)
            if result:
                if not self.is_bot_game():
                    self.show_maps()
                return result
            self.shot_was_made(False, team)
            if not self.is_bot_game():
                self.show_maps()
            return SHOT_MISSED
        return SHOT_WRONG_COORDINATES

    @staticmethod
    def process_drawn_ships(attack_result, ship, team):
        if attack_result == SHOT_DRAWN_SHIP:
            for point in ship.points:
                team.field_of_shots[point.x + point.y * MAP_SIZE] = Shots.DRAWN
        team.process_drawn_ships()

    @staticmethod
    def is_shot_was_made(hit_point, team):
        shot = team.field_of_shots[hit_point.x + hit_point.y * MAP_SIZE]
        print("\t\tSHOT {} WAS MADE ???? -> {}\n".format(hit_point, shot != Shots.NONE))
        return shot != Shots.NONE

    @staticmethod
    def is_shot_correct(hit_point, team):
        print("\n\t\tCHECKING HIT_POINT FOR CORRECTNESS ---> {}!!!!!!!!!!!\n\n".format(hit_point))

        for i in range(hit_point.y - 1, hit_point.y + 2):
            for j in range(hit_point.x - 1, hit_point.x + 2):
                p = _Point.normalize_point(_Point(j, i, hit_point.value, False))
                print("\n\t\tChecking nearby point for CORRECTNESS - {}\n\n".format(p))

                if team.field_of_shots[p.x + p.y * MAP_SIZE] == Shots.DRAWN:

                    print("\t\tpoint {} --- > INCORRECT!!!!\n\n".format(hit_point))
                    return False

        print("\t\tpoint {} -> Correct!\n\n".format(hit_point))
        return True

    def process_shot(self, hit_point, team):
        if self.is_shot_was_made(hit_point, team):
            return SHOT_ALREADY_MADE, None
        for rank in shipRanks:
            for ship in team.ships[rank]:
                was_hit, msg = ship.try_attack(hit_point)
                if was_hit:
                    team.field_of_shots[hit_point.x + hit_point.y * MAP_SIZE] = Shots.DRAWN if msg == SHOT_DRAWN_SHIP else Shots.HIT
                    self.shot_was_made(was_hit, team)
                if msg:
                    return msg, ship
        team.field_of_shots[hit_point.x + hit_point.y * MAP_SIZE] = Shots.MISSED
        return None, None

    def process_bot_turn(self):
        if not self.bot_turn:
            return

        active, questioned = self.session_is_active()

        if self.hit_was_made and not questioned:
            self.show_maps("")
            self.send_message(uid=self.uid, chat_id=self.chat_id, message=u"Могёте стрелять ещё")
        else:
            result = self.attack("", True)
            self.send_message(uid=self.uid, chat_id=self.chat_id, message=result)
            if not questioned:
                while result == SHOT_DRAWN_SHIP or result == SHOT_SHIP_WAS_HIT:
                    result = self.attack("", True)
                    self.send_message(uid=self.uid, chat_id=self.chat_id, message=result)
            self.show_maps("")
        self.bot_turn = False

    @staticmethod
    def save_game_results(file_name, data):
        try:
            with open(file_name, 'w') as outfile:
                yaml.dump(data, outfile, default_flow_style=True)
        except Exception as e:
            print "Exception occurred while saving game results: {}" \
                .format(e.message)

    @need_game_session
    def stop_game_session(self, message=""):
        # Check the winner, save game data, send message about game ending to both players,
        # delete both teams from self.teams, and current game from self.games

        if not self.game_context:
            self.active_sessions = [session for session in self.active_sessions if session["session_uid"] != self.uid]
            return SESSION_STOPPED_MSG.format(self.uid)

        team_name = self.get_team_name()
        opponent_name = self.get_opponent_name(team_name)

        if team_name:
            game, i = self.get_game_data(team_name=team_name)

            if game and self.is_game_started():
                gc = self.game_context
                winner_name = self.check_winner()
                if not winner_name:
                    winner_name = opponent_name

                winner = gc.this_team if gc.this_team_name == winner_name else gc.opponent
                looser = gc.this_team if gc.this_team_name != winner_name else gc.opponent

                game_finished = datetime.now().strftime("%d.%m.%Y %H.%M.%S")
                data = {"winner": winner.team_name,
                        "looser": looser.team_name,
                        "winner_score": winner.score,
                        "looser_score": looser.score,
                        "game_started": game["game_started_datetime"],
                        "game_finished": game_finished}

                file_name = self.directory + "/{}_vs_{}_{}.yaml".format(winner.cap_uid, looser.cap_uid, game_finished)

                GameManager.save_game_results(file_name, data)

                if not winner.bot_game:
                    self.send_message(self.teams[winner_name]["team_uid"],
                                      self.teams[winner_name]["team_chat_id"],
                                      u"Это победа! Грац! Ваши очки - {}, очки оппонента - {}"
                                      .format(unicode(data["winner_score"]), unicode(data["looser_score"])))
                if not looser.bot_game:
                    self.send_message(self.teams[looser.team_name]["team_uid"],
                                      self.teams[looser.team_name]["team_chat_id"],
                                      u"Луууузеерыы! (Вы продули...=/) Ваши очки - {}, очки оппонента - {}"
                                      .format(unicode(data["looser_score"]), unicode(data["winner_score"])))

                self.active_sessions = [session for session in self.active_sessions if
                                        (not winner.bot_game and session["session_uid"] != self.teams[winner_name]["team_uid"]) and
                                        (not looser.bot_game and session["session_uid"] != self.teams[looser.team_name]["team_uid"])]

            if i >= 0:
                self.games = [g for j, g in enumerate(self.games) if j != i]

            try:
                if team_name:
                    del self.teams[team_name]
                if opponent_name:
                    del self.teams[opponent_name]
            except Exception as e:
                print "Exception while deleting teams - {}".format(e.message)

        self.active_sessions = [session for session in self.active_sessions if session["session_uid"] != self.uid]
        self.game_context.this_team = None
        self.game_context.opponent = None

        return SESSION_STOPPED_MSG.format(self.uid)

    #   game commands   ================================================================================================

    def shot_was_made(self, hit, team):
        gc = self.game_context
        if not gc or not gc.this_team:
            return
        team.question_answered = False
        active, questioned = self.session_is_active()
        team.score += gc.this_team.score_per_hit if hit else 0
        team.score += 1 if hit and (not questioned or self.is_bot_game()) else 0
        team.score_per_hit = 0
        self.bot_turn = self.is_bot_game()
        self.hit_was_made = hit
        print "Team uid {} score - {}".format(gc.this_team.cap_uid, gc.this_team.score)

    def remove_game_data(self, team_name=None):
        team_name = self.get_team_name() if not team_name else team_name
        self.games = [game for game in self.games
                      if game["team_name"] != team_name and game["opponent_team_name"] != team_name]

    def remove_team(self, team_name=None):
        team_name = self.get_team_name() if not team_name else team_name
        try:
            del self.teams[team_name]
            return True
        except Exception as e:
            print "Exception while deleting team - {}".format(e.message)
            return False

    def is_bot_game(self):
        game, i = self.get_game_data()
        if game:
            return try_get_data(game, "bot_game")
        return False

    def get_game_data(self, uid=None, team_name=None, this_team_only=False, only_opponent=False):
        team_name = self.get_team_name(uid) if not team_name else team_name
        if not team_name:
            return None, -1
        for i, game in enumerate(self.games):
            if (not only_opponent and game["team_name"] == team_name) or \
                    (not this_team_only and game["opponent_team_name"] == team_name):
                return game, i
        return None, -1

    @need_game_session
    @need_game_context
    @need_game_started
    def check_winner(self):
        return self.game_context.check_winner()

    @staticmethod
    def check_list(container, data_type):
        if len(container) < 1:
            return True, -1
        for i, data in enumerate(container):
            if not isinstance(data, data_type):
                return False, i
        return True, -1

    def check_games(self):
        ok, i = GameManager.check_list(self.games, dict)
        if not ok and i >= 0:
            self.games = [game for j, game in enumerate(self.games) if j != i]

    def load(self):
        try:
            with open(self.directory + "/seabattle_game.yaml", 'r') as stream:
                data = yaml.load(stream)
                self.teams = data["teams"]
                self.games = data["games"]
                self.active_sessions = data["active_sessions"]
                print("Loaded seabattle_game.yaml, active_sessions count - {}\n".format(len(self.active_sessions)))
        except Exception as e:
            self.teams = {}
            self.games = []
            self.active_sessions = []
            print e.message

    def save(self):
        with open(self.directory + "/seabattle_game.yaml", 'w') as outfile:
            data = {"teams": self.teams, "games": self.games, "active_sessions": self.active_sessions}
            yaml.dump(data, outfile, default_flow_style=True)
            print("Saved seabattle_game.yaml, active_sessions count - {}\n".format(len(self.active_sessions)))

    def session_is_active(self):
        if not self.uid or len(self.active_sessions) == 0:
            return False, False
        try:
            for session in self.active_sessions:
                if session["session_uid"] == self.uid:
                    return True, bool(session["questioned_game"])
        except Exception as e:
            print "Exception occurred while checking session - {}".format(e.message)
        return False, False

    def send_message(self, uid, chat_id, message, attachments=None):
        try:
            if not message:
                message = ""
            if chat_id:
                self.vk_user.send_message(text=message, chatid=chat_id, attachments=attachments)
            else:
                self.vk_user.send_message(text=message, userid=uid, chatid=None, attachments=attachments)
        except Exception as e:
            print "Exception occured while sending message, sea_battle.game_manager - {}".format(e.message)

    def generate_bot_field(self):
        while True:
            field = Team.generate_random_map()
            if len(field) != MAP_SIZE * MAP_SIZE:
                continue
            resp = self.game_context.opponent.parse_fields(field)
            if resp == GOOD_MAP_MSG:
                return field

    def start_game_with_bot(self):
        gc = self.game_context
        t_team_name = gc.this_team_name
        gc.bot_game = True
        gc.op_team_name = "tulen"
        gc.opponent = gc.create_team(gc.op_team_name, gc.op_team_name, True)
        gc.opponent.field = self.generate_bot_field()

        game = {"team_name": t_team_name,
                "opponent_team_name": gc.op_team_name,
                "bot_game": True,
                "game_started_datetime": datetime.now().strftime("%d.%m.%Y %H:%M:%S"),
                "game_started": True,
                "winner": ""}

        self.games.append(game)
        return GAME_STARTED_WITH_BOT_MSG

    def start_game_with(self, op_team_name):
        gc = self.game_context
        t_team_name = gc.this_team_name
        if op_team_name == t_team_name:
            return u"Вы не можете играть с самим собой!"

        game, i = self.get_game_data(team_name=op_team_name)

        if game or i >= 0:
            if game["game_started"]:
                return u"Команда {} уже играет с другой командой, выберите друго оппонента".format(op_team_name)
            if game["team_name"] != t_team_name and game["opponent_team_name"] != t_team_name:
                return u"Команда {} ожидает другого оппонента, не вас".format(op_team_name)
            if game["team_name"] == t_team_name:
                return u"Вы уже ожидаете оппонента {}".format(op_team_name)
            if game["opponent_team_name"] == t_team_name:
                game["winner"] = ""
                game["game_started_datetime"] = datetime.now().strftime("%d.%m.%Y %H:%M:%S")
                game["game_started"] = True
                self.games[i] = game

                gc.op_team_name = op_team_name
                opponent_team = self.teams[op_team_name]
                gc.opponent, tmp = GameContext.load_team_data(try_get_data(opponent_team, "team_uid"), self.directory)
                GameContext.save_team_data(gc.opponent, gc.this_team, self.directory)

                self.send_message(try_get_data(opponent_team, "team_uid"),
                                  try_get_data(opponent_team, "team_chat_id"),
                                  GAME_STARTED_MSG.format(t_team_name))

                return GAME_STARTED_MSG.format(op_team_name)

        game = {"team_name": t_team_name,
                "opponent_team_name": op_team_name,
                "bot_game": False,
                "game_started": False,
                "winner": "",
                "game_started_datetime": None}

        self.games.append(game)
        opponent_team = self.teams[op_team_name]
        message = u"Команда {} ожидает вас в игре Морской Бой! Для начала игры введите команду {} {}" \
            .format(t_team_name, gameRequest_command, t_team_name)
        self.send_message(try_get_data(opponent_team, "team_uid"),
                          try_get_data(opponent_team, "team_chat_id"),
                          message)
        return WAITING_FOR_OPPONENT_MSG.format(op_team_name)

    def is_answer_correct(self, answer, q_number):
        return answer == self.questions[q_number].values()[0]

    def is_game_started(self):
        game, i = self.get_game_data()
        if not game:
            return False
        return try_get_data(game, "game_started")

    def question_was_answered(self, question_id, correct):
        gc = self.game_context
        if question_id in gc.this_team.answered_questions:
            return QUESTION_ALREADY_ANSWERED.format(question_id + 1)

        score_per_hit = RIGHT_ANSWER_SCORE if correct else WRONG_ANSWER_SCORE
        gc.this_team.score_per_hit = score_per_hit
        gc.this_team.question_answered = True
        gc.this_team.answered_questions.append(question_id)

        if correct:
            return CORRECT_ANSWER_MSG.format(score_per_hit)
        return INVALID_ANSWER_TEXT_MSG

    #   ================================= GET from GameManager =========================================================

    def get_team_name(self, uid=None):
        uid = self.uid if not uid else uid
        for team_name in self.teams.keys():
            if self.teams[team_name]["team_uid"] == uid:
                return team_name
        return ""

    def get_opponent_name(self, team_name, only_opponent=False):
        if not team_name:
            return None
        for game in self.games:
            if game["team_name"] == team_name:
                return game["opponent_team_name"]
            if not only_opponent and game["opponent_team_name"] == team_name:
                return game["team_name"]
        return None

    def get_team_cap_uid(self, team_name):
        if not team_name or not self.teams:
            return ""
        if self.is_bot_game():
            return "tulen"
        return try_get_data(self.teams[team_name], "team_uid")

    def get_game_winner(self):
        game, i = self.get_game_data()
        if game:
            return game["winner"]
        return ""

    #   ================================= GET from GameManager =========================================================
