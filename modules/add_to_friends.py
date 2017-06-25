#!/usr/bin/python
# -*- coding: utf-8 -*-
from io import StringIO
from threading import Timer

# logging.basicConfig()
# log = logging.getLogger(__name__)
import requests
from . import pixelsort
from PIL import Image
from vk.exceptions import VkAPIError
import random


class Processor:
    def __init__(self, user):
        print('Add to friends module ctor called!')
        self.user = user
        self.mc = 0
        self.uids = set()
        self.blocked = False

    def process_message(self, message, chatid, userid):
        print('Add to friends, process_message mc: {} for chat_id: {}, user_id: {}'.format(self.mc, chatid, userid))
        user_id = message["user_id"]
        self.uids.add(user_id)
        self.uids.add(userid)
        self.mc += 1

        if self.mc % random.randint(2, 4) != 0:
            return

        print('Add to friends process_message called with user_id: {}'.format(user_id))
        self.mc = 0
        uids = self.user.getRequests()
        for uid in uids:
            if self.user.friendAdd(uid):
                print("Send a friend req for  id{}".format(uid))
                self.pixelsort_and_post_on_wall(uid)

        if self.mc < 10:
            return

        if self.blocked:
            return

        self.mc = 0
        fs = self.user.friendStatus(",".join([str(uid) for uid in self.uids]))
        for item in fs:

            if item["friend_status"] == 0:
                try:
                    if self.user.friendAdd(item["user_id"]):

                        print("Send a friend req for  id{}".format(user_id))
                        self.pixelsort_and_post_on_wall(item["user_id"])
                    else:
                        print("Failed to send a friend req for  id{}".format(user_id))
                except VkAPIError as e:

                    if e.code != 175 and e.code != 176:
                        self.blocked = True
                        t = Timer(60 * 60 * 2, self.unblock, [])
                        t.start()
                        raise

    def unblock(self):

        self.blocked = False
        self.uids = set()
        self.mc = 0

    def pixelsort_and_post_on_wall(self, user_id):
        user = self.user.getUser(user_id, "photo_max_orig", name_case="Nom")
        photo_url = user["photo_max_orig"]
        r = requests.get(photo_url)

        print('pixelsort_and_post_on_wall, r:{}, r.content: {}'.format(r, r.content))

        i = Image.open(StringIO(r.content.decode('utf-8')))
        img_file = "./files/friend{}.jpg".format(user_id)
        i.save(img_file)

        pixelsort.glitch_an_image(img_file)

        wall_attachments = self.user.upload_images_files_wall([img_file, ])
        self.user.post(u"Привет, {} {}".format(user["first_name"], user["last_name"]), attachments=wall_attachments,
                       chatid=None, userid=user_id)
