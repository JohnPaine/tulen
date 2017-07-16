#!/usr/bin/python
# -*- coding: utf-8 -*-

import logging
import yaml
from . import sea_battle_package as sbp
import os

logger = logging.getLogger('seal')

CONFIG_FILE = "conf.yaml"


class Processor:
    def __init__(self, vk_user):
        self.config = yaml.load(open(vk_user.module_file("sea_battle", CONFIG_FILE)))
        self.user = vk_user

        directory = "./files/sea_battle_data_{}".format(vk_user.user_id)
        try:
            if not os.path.exists(directory):
                os.makedirs(directory)
        except Exception as e:
            print("Exception occurred while trying to create directory {} - {}".format(directory, e))

        # array of dicts {int question number: str answer}
        questions = self.config["questions"]
        print("Sea battle process ctor, questions: {}".format(questions))

        self.game_manager = sbp.GameManager(vk_user, questions, directory)
        print(self.config)

        # map of request_text - handlers
        self.mapper = {sbp.start_game_processing_command: self.start_game_session,
                  sbp.start_questioned_game_processing_command: self.start_questioned_game_session,
                  sbp.stop_game_processing_command: self.stop_game_session,
                  sbp.answer_command: self.answer,
                  sbp.gameRequest_command: self.game_request,
                  sbp.bot_gameRequest_command: self.bot_game_request,
                  sbp.attack_command: self.attack,
                  sbp.questions_command: self.questions,
                  sbp.loadMap_command: self.load_map,
                  sbp.loadRandomMap_command: self.load_random_map,
                  sbp.registerTeam_command: self.register,
                  sbp.showTeams_command: self.show_teams,
                  sbp.showGameCommands_command: self.show_commands,
                  sbp.showMaps_command: self.show_maps}

    def start_game_session(self, msg):
        return self.game_manager.start_game_session(msg)

    def start_questioned_game_session(self, msg):
        return self.game_manager.start_questioned_game_session(msg)

    def show_commands(self, msg):
        return self.game_manager.show_commands(msg)

    def show_teams(self, msg):
        return self.game_manager.show_teams(msg)

    def register(self, msg):
        return self.game_manager.register_team(msg)

    def questions(self, msg):
        return self.game_manager.get_questions(msg)

    def load_map(self, msg):
        return self.game_manager.load_map(msg)

    def load_random_map(self, msg):
        return self.game_manager.load_random_map(msg)

    def game_request(self, msg):
        return self.game_manager.game_request(msg)

    def bot_game_request(self, msg):
        return self.game_manager.bot_game_request(msg)

    def show_maps(self, msg):
        return self.game_manager.show_maps(msg)

    def answer(self, msg):
        return self.game_manager.parse_answer(msg)

    def attack(self, msg):
        return self.game_manager.attack(msg)

    def stop_game_session(self, msg):
        return self.game_manager.stop_game_session(msg)

    def handler(self, message):
        # dummy answer (if nothing fit or session ain't started)
        def dummy():
            def call():
                return ""

        # wrapper for method with param
        def wrapper(funk, msg):
            def call():
                return funk(msg)
            return call

        # return necessary method
        for k, v in self.mapper.items():
            if k in message:
                return wrapper(v, message)

        return dummy

    def process_message(self, message, chatid, userid):
        msg = message["body"].lower()
        game_command = False

        for item in self.mapper:
            if msg.startswith(item):
                game_command = True
                break
        if not game_command:
            return False

        with self.game_manager(message, userid, chatid):
            logger.info(msg)
            response_text = self.handler(msg)()
            if response_text:
                self.user.send_message(text=response_text, userid=userid, chatid=chatid)
                return True
            return False
