#!/usr/bin/python
# -*- coding: utf-8 -*-

import random
import re
import traceback
# from multiprocessing import Lock
import os

from collections import defaultdict

import yaml

# save_lock = Lock()

CONFIG_FILE = "conf.yaml"


class ChatHistory:
    # if disinterest_counter reaches max - dialog may be deleted as users ain't interested in it
    DISINTEREST_COUNTER_MAX = 20

    def __init__(self, dialog_id=0, uid=0, chat_id=0):
        self.id = dialog_id
        self.user_id = uid
        self.chat_id = chat_id
        # dialog pattern id from the config file - only 1 dialog pattern available for each chat
        self.dialog_pattern_id = 0
        self.stage_num = 0
        # counts how many times user not replied according to the pattern
        self.disinterest_counter = 0

    def serialize(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "chat_id": self.chat_id,
            "dialog_pattern_id": self.dialog_pattern_id,
            "stage_num": self.stage_num,
            "disinterest_counter": self.disinterest_counter
        }

    def deserialize(self, data):
        try:
            self.id = data["id"]
            self.user_id = data["user_id"]
            self.chat_id = data["chat_id"]
            self.dialog_pattern_id = data["dialog_pattern_id"]
            self.stage_num = data["stage_num"]
            self.disinterest_counter = data["disinterest_counter"]
            return True
        except:
            traceback.print_exc()
            return False


class DialogData:
    def __init__(self, vk_user, config, directory):
        self.directory = directory
        self.dialogs = defaultdict(ChatHistory)
        self.config = config
        self.vk_user = vk_user

    def __enter__(self):
        pass

    def __call__(self):
        self.load_dialogs()
        return self

    def __exit__(self, _type, _value, _traceback):
        self.save_dialogs()

    def serialize(self):
        data = {}
        for dialog_id, chat_history in self.dialogs.items():
            data[dialog_id] = chat_history.serialize()
        return data

    def deserialize(self, data):
        self.dialogs = defaultdict(ChatHistory)
        if not data or not len(data):
            return
        for dialog_id, chat_history in data.items():
            self.dialogs[dialog_id].deserialize(chat_history)

    @staticmethod
    def get_id(uid, chat_id):
        if not chat_id:
            return uid
        return -1 * chat_id

    def load_dialogs(self):
        try:
            data_file_name = self.directory + "/dialogs_data.yaml"
            if not os.path.isfile(data_file_name):
                return False
            with open(data_file_name, 'r') as stream:
                self.deserialize(yaml.load(stream))
                return True
        except Exception as e:
            print("Exception occurred while loading dialogs data: {}".format(e))
            self.dialogs = defaultdict(ChatHistory)
            traceback.print_exc()
            return False

    def save_dialogs(self):
        try:
            data_file_name = self.directory + "/dialogs_data.yaml"
            if not len(self.dialogs):
                try:
                    os.remove(data_file_name)
                except OSError:
                    pass
                return False
            if not os.path.exists(self.directory):
                os.makedirs(self.directory)
                os.chmod(self.directory, 0o666)
            with open(data_file_name, 'w') as outfile:
                yaml.dump(self.serialize(), outfile, default_flow_style=True)
                os.chmod(data_file_name, 0o666)
                return True
        except Exception as e:
            print("Exception occurred while saving dialogs data: {}".format(e))
            traceback.print_exc()
            return False

    def dialog_exists(self, uid, chat_id):
        dialog_id = DialogData.get_id(uid, chat_id)
        return dialog_id in self.dialogs

    def get_dialog(self, uid, chat_id):
        if not self.dialog_exists(uid, chat_id):
            return None
        return self.dialogs[DialogData.get_id(uid, chat_id)]

    def create_dialog(self, uid, chat_id):
        if self.dialog_exists(uid, chat_id):
            return self.dialogs[DialogData.get_id(uid, chat_id)]
        dialog_id = DialogData.get_id(uid, chat_id)
        return ChatHistory(dialog_id, uid, chat_id)

    def finish_dialog(self, uid, chat_id):
        try:
            dialog_id = self.get_id(uid, chat_id)
            if dialog_id in self.dialogs:
                del self.dialogs[dialog_id]
        except:
            traceback.print_exc()

    def continue_dialog(self, uid, chat_id, message):
        chat_history = self.get_dialog(uid, chat_id)
        dialog_pattern = self.config[chat_history.dialog_pattern_id]
        msg = message["body"].lower()

        def check_reply(regexp_name):
            reply_regexps = dialog_pattern.get(regexp_name, list())
            for word in reply_regexps:
                pattern_object = re.compile(word, flags=re.IGNORECASE | re.UNICODE)
                if pattern_object.match(msg):
                    return True
            return False

        def check_dialog_finished():
            return "stage_{}_reply_positive_regexps".format(chat_history.stage_num) not in dialog_pattern and \
                   "stage_{}_reply_negative_regexps".format(chat_history.stage_num) not in dialog_pattern

        if check_dialog_finished():
            self.finish_dialog(uid, chat_id)
            return False

        if check_reply("stage_{}_reply_positive_regexps".format(chat_history.stage_num)):
            chat_history.stage_num += 1
            return self.launch_message_for_stage(uid, chat_id, chat_history.stage_num,
                                                 chat_history.dialog_pattern_id, chat_history)

        if check_reply("stage_{}_reply_negative_regexps".format(chat_history.stage_num)):
            return self.dialog_stop_requested(uid, chat_id, chat_history.stage_num,
                                              chat_history.dialog_pattern_id)

        chat_history.disinterest_counter += 1
        if ChatHistory.DISINTEREST_COUNTER_MAX < chat_history.disinterest_counter:
            self.finish_dialog(uid, chat_id)
            return False
        return False

    def dialog_stop_requested(self, uid, chat_id, stage_num, dialog_pattern_id):
        stop_messages = self.config[dialog_pattern_id].get("stage_{}_stop_messages".format(stage_num), list())
        self.finish_dialog(uid, chat_id)
        if len(stop_messages) > 0:
            self.vk_user.send_message(text=random.choice(stop_messages), chatid=chat_id, userid=uid)
            return True
        return False

    def launch_message_for_stage(self, uid, chat_id, stage_num, dialog_pattern_id, chat_history=None):
        dialog_pattern = self.config[dialog_pattern_id]
        launcher_messages = dialog_pattern.get("stage_{}_launcher_messages".format(stage_num), list())
        if not len(launcher_messages):
            self.finish_dialog(uid, chat_id)
            return False

        self.vk_user.send_message(text=random.choice(launcher_messages), chatid=chat_id, userid=uid)

        if not chat_history:
            chat_history = self.create_dialog(uid, chat_id)

        chat_history.stage_num = stage_num
        chat_history.dialog_pattern_id = dialog_pattern_id
        self.dialogs[chat_history.id] = chat_history

        return True

    def start_dialog(self, uid, chat_id, dialog_pattern_id, message):
        stage_num = 1
        return self.launch_message_for_stage(uid, chat_id, stage_num, dialog_pattern_id)

    def try_start_dialog(self, uid, chat_id, message):
        msg = message["body"].lower()

        for dialog_pattern_id, dialog_pattern in self.config.items():
            starter_words = dialog_pattern.get("dialog_starter_words_regexps", None)
            if starter_words:
                for word in starter_words:
                    pattern_object = re.compile(word, flags=re.IGNORECASE | re.UNICODE)
                    if pattern_object.match(msg):
                        return self.start_dialog(uid, chat_id, dialog_pattern_id, message)

            start_without_words = dialog_pattern.get("start_without_starter_words", False)
            if not start_without_words:
                continue
            if random.randint(0, 100) > 5:
                continue
            return self.start_dialog(uid, chat_id, random.choice(list(self.config)), message)

        return False


class Processor:
    def __init__(self, vk_user):
        config = yaml.load(open(vk_user.module_file("dialogs", CONFIG_FILE)))

        directory = "./files/dialogs_data_{}".format(vk_user.user_id)
        self.dialog_data = DialogData(vk_user, config, directory)

    def process_message(self, message, chat_id, user_id):
        with self.dialog_data():
            if self.dialog_data.dialog_exists(user_id, chat_id):
                return self.dialog_data.continue_dialog(user_id, chat_id, message)
            return self.dialog_data.try_start_dialog(user_id, chat_id, message)
