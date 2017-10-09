#!/usr/bin/python
# -*- coding: utf-8 -*-

import random

commands = [u"{SealName}, покинь беседу"]

confirm_questions = [u"Вы точно хотите, чтобы я ушёл?"]

class LeaveState:
    def __init__(self):


    def process_user_msg(self, message):



class Processor:
    def __init__(self, user):
        self.user = user

        self.user_name = Processor.get_user_name(user)
        self.replies = {}

    @staticmethod
    def get_user_name(vk_user):
        user_info = vk_user.getUser(vk_user.user_id)
        first_name = user_info['first_name']
        last_name = user_info['last_name']
        return u"{} {}".format(first_name, last_name)

    @staticmethod
    def get_id(uid, chat_id):
        if not chat_id:
            return uid
        return -1 * chat_id

    @staticmethod
    def is_request(message, user_name):
        for c in commands:
            if c.format(SealName=user_name) in message:
                return True
        return False

    def process_message(self, message, chat_id, user_id):
        message_body = message["body"].lower()
        if not self.is_request(message_body):
            return False

        _id = self.get_id(user_id, chat_id)

        if _id not in self.replies or self.replies[_id] <= 0:
            self.replies[_id] = 30
            self.user.send_message(help_message_full, chatid=chat_id, userid=user_id)
        else:
            self.replies[_id] -= 1
            self.user.send_message(random.choice(help_message_short_replies), chatid=chat_id, userid=user_id)
        return True