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

no_chat_responses = [
    u"да ты, ты",
    u"в зеркало смотреться не пробовал?",
    u"тут больше никого нет",
    u"это не я",
    u"возможно это я",
    u"я тебе ванга штоле?! спроси чо полегче",
    u"хуй знает, наверно это ты",
    u"это всё Нэвэльны",
    u"ну не я же",
    u"не ебу о ком ты",
    u"может это ты?",
    u"не скажу",
    u"ну не я же",
    u"кто-то из нас",
    u"кто, если не мы?",
    u"точно не я"
]


class Processor:
    def __init__(self, vk_user):
        self.user = vk_user
        self.config = yaml.load(open(vk_user.module_file("who", CONFIG_FILE)))

    def respond(self, user_id, chat_id, query):
        def response_unknown():
            if random.randint(1, 100) < 50:
                self.user.send_message(text=u"", send_sticker=True, chatid=chat_id, userid=user_id)
            self.user.send_message(text=random.choice(no_chat_responses), send_sticker=False, chatid=chat_id, userid=user_id)
            return True

        if not chat_id or random.randint(1, 100) < 30:
            return response_unknown()

        users = self.user.get_chat(chat_id, fields="sex")['users']
        user = random.choice(users)
        first_name = user["first_name"]
        last_name = user["last_name"]

        sentence_start = random.choice(self.config["replies"])

        self.user.send_message(text=u"{} {} {}".format(sentence_start, first_name, last_name),
                               chatid=chat_id, userid=None)
        return True

    def process_message(self, message, chat_id, user_id):
        message_body = message["body"].lower()

        for t in triggers:
            if message_body.startswith(t):
                return self.respond(user_id, chat_id, message_body[len(t):])
