#!/usr/bin/python
# -*- coding: utf-8 -*-
import random
from threading import Timer
import traceback

# logging.basicConfig()
# log = logging.getLogger(__name__)
from vk.exceptions import VkAPIError


class Processor:
    def __init__(self, user):
        print('Add to friends module ctor called!')
        self.user = user
        self.mc = 0
        self.uids = set()
        self.blocked = False
        self.failed_users = set()

    def process_message(self, message, chatid, userid):
        user_id = message["user_id"]
        self.uids.add(user_id)
        self.uids.add(userid)
        self.mc += 1

        if self.mc % random.randint(2, 4) != 0:
            return

        # print('Add to friends process_message called with user_id: {}'.format(user_id))
        self.mc = 0
        uids = self.user.getRequests()
        for uid in uids:
            try:
                if uid in self.failed_users:
                    continue
                if self.user.friendAdd(uid):
                    print("Sent a friend req for id{}".format(uid))
                    self.user.pixelsort_and_post_on_wall(uid)
            except Exception as e:
                print('Failed to add user {}, exception: {}'.format(uid, e))
                self.failed_users.add(uid)
                traceback.print_exc()

        if self.mc < 10:
            return

        if self.blocked:
            return

        self.mc = 0
        fs = self.user.friendStatus(",".join([str(uid) for uid in self.uids]))
        for item in fs:

            if item["friend_status"] == 0:
                try:
                    uid = item["user_id"]
                    if uid in self.failed_users:
                        continue
                    if self.user.friendAdd(uid):

                        print("Sent a friend req for  id{}".format(uid))
                        self.user.pixelsort_and_post_on_wall(uid)
                    else:
                        print("Failed to send a friend req for  id{}".format(uid))
                        self.failed_users.add(uid)

                except VkAPIError as e:

                    if e.code != 175 and e.code != 176:
                        self.blocked = True
                        t = Timer(60 * 60 * 2, self.unblock, [])
                        t.start()
                        traceback.print_exc()
                except Exception as e:
                    print("Something wrong in add_to_friends module, e: {}".format(e))
                    traceback.print_exc()

    def unblock(self):

        self.blocked = False
        self.uids = set()
        self.mc = 0
