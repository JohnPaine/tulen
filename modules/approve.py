#!/usr/bin/python
# -*- coding: utf-8 -*-

import random
import re
import traceback
import os

import yaml

CONFIG_FILE = "conf.yaml"


class Processor:
    def __init__(self, vkuser):
        self.user = vkuser
        self.config = yaml.load(open(vkuser.module_file("approve", CONFIG_FILE)))

    def respond(self, word, chat_id, user_id):
        replies = [l.strip() for l in open(self.user.module_file("approve", self.config[word]["dict"])).readlines()]
        reply = random.choice(replies)
        rand = random.randint(1, 100)
        if 35 <= rand <= 65:
            try:
                self.user.send_message(text="", send_sticker=True, chatid=chat_id, userid=user_id)
            except:
                traceback.print_exc()

        if reply.startswith("img:"):
            img_file = self.user.module_file("approve", reply[reply.rindex("img"):])
            attachment = self.user.upload_images_files([img_file, ])
            self.user.send_message(text="", attachments=attachment, chatid=chat_id, userid=user_id)
        # elif reply.startswith("folder_imgs"):
        #     folder = self.user.module_file("approve", reply[reply.rindex("folder_imgs"):])
        #     img_list = os.listdir(folder)
        #     img_file = self.user.module_file("approve", random.choice(img_list))
        #     attachment = self.user.upload_images_files([img_file, ])
        #     self.user.send_message(text="", attachments=attachment, chatid=chat_id, userid=user_id)
        else:
            self.user.send_message(text=reply, chatid=chat_id, userid=user_id)

    def process_message(self, message, chatid, userid):
        responded = False

        for word in self.config.keys():

            message_body = message["body"].lower()

            prog = re.compile(word)

            if prog.match(message_body):
                self.respond(word, chatid, userid)
                responded = True

        if chatid is None and not responded:
            pu_dicts = [k for k in self.config.keys() if self.config[k].get("private_use", False)]
            self.respond(random.choice(pu_dicts), chatid, userid)
            return True
        return True
