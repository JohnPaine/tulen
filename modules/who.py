#!/usr/bin/python
# -*- coding: utf-8 -*-

import random

import yaml

CONFIG_FILE = "conf.yaml"

triggers = [u"тюлень, кто",
            u"тюлень кто",
            u"тюля, кто"
            u"тюля кто",
            u"кто", ]


class Processor:
    def __init__(self, vk_user):
        self.user = vk_user
        self.config = yaml.load(open(vk_user.module_file("who", CONFIG_FILE)))

    def respond(self, chat_id, query):
        users = self.user.get_chat(chat_id)['users']
        user = random.choice(users)
        first_name = user["first_name"]
        last_name = user["last_name"]

        sentence_start = random.choice(self.config["replies"])

        self.user.send_message(text=u"{} {} {}".format(sentence_start, first_name, last_name), chatid=chat_id, userid=None)

        return True

    def process_message(self, message, chat_id, user_id):
        message_body = message["body"].lower()

        for t in triggers:
            if message_body.startswith(t):
                return self.respond(chat_id, message_body[len(t):])
