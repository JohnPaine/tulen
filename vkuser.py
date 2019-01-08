# coding: utf-8
import time
import json
import requests
import io
import sys
import os
import logging
import random
import threading
from multiprocessing.pool import ThreadPool
import multiprocessing
import queue
import utils
import vkrequest
import vk_api
from vk_api.bot_longpoll import VkBotLongPoll, VkBotEventType

sys.path.append("./modules")
logger = logging.getLogger('tulen')
logger.setLevel(logging.DEBUG)


class VkBotLongPollRaw(VkBotLongPoll):
    CLASS_BY_EVENT_TYPE = {}


class VkUser(object):
    # return the file form config directory for module name
    # used by modules
    def module_file(self, modname, filename):
        return os.path.join(self.config.get("modules_config_dir", "config"), modname, filename)

    def init_globals(self):
        # for proper random
        random.seed(time.time())

        # captcha init: if no captcha section in config, pass it
        captcha_config = self.config.get("anticaptcha", None)
        if not captcha_config:
            logger.warning("Anticaptcha cant be intialized: no config")

        else:

            service = captcha_config["service"]
            creds = captcha_config["credentials"]
            vkrequest.init_captcha(service, creds)
            logger.info("Captcha [{}] initialized. balance: {}".format(service,
                                                                       vkrequest.captcha.balance()))

        # enable ratelimiting
        vkrequest.run_rate_limit_dispatcher()

        logger.info("Rate-limit dispatcher started")

        logger.info("Global systems initialized")

    def init_vk_session(self):
        if self.testmode:
            self.api = None
            logger.info("VK Session: test mode")
        else:
            self.my_uid = self.config["access_token"]["user_id"]
            self.user_id = self.my_uid

            if not self.my_uid:
                raise RuntimeError("Access config: user_id not defined")

            self.vk_session = vk_api.VkApi(token=self.config["access_token"]["value"])
            self.longpoll = VkBotLongPollRaw(self.vk_session, self.my_uid)
            self.api = self.vk_session.get_api()
            logger.info("VK Session: real mode [{}]".format(self.my_uid))

    def init_modules(self):
        modules_list_file = self.config.get("enabled_modules_list", None)

        if not modules_list_file:
            mods = self.config.get("enabled_modules", None)
        else:
            mods = [l.strip() for l in open(modules_list_file).readlines()]

        mods = [m for m in mods if not m.startswith("#")]
        if not mods:
            raise RuntimeError("Can't find any module to load!")

        logger.info("Enabled modules: [{}]".format(",".join(mods)))

        self.load_modules(mods)
        logger.info("All modules loaded.")

    def load_modules(self, mod_list):
        self.modules = {"global": [], "unique": [], "parallel": []}

        def add_module(modif, modproc):
            modules = self.modules.get(modif, [])
            modules.append(modproc)
            self.modules[modif] = modules

        for module in mod_list:
            data = module.split()
            modif = "parallel"
            module = data[0]
            if len(data) > 1:
                modif = data[0]
                module = data[1]

            package = __import__("modules" + "." + module)
            processor = getattr(package, module)
            modprocessor = processor.Processor(self)

            add_module(modif, modprocessor)

            logger.info("Loaded module: [{}] as {}".format(
                "modules" + "." + module, modif))

    def init_multithreading(self):
        self.msg_queue = {}

        # create message queue: general (first step for uniq modules)
        self.msg_queue["general"] = queue.Queue()
        # create message queues: paralel (for parallel message processing)
        self.msg_queue["parallel"] = queue.Queue()

        self.msg_processors = {}

        # create threads for general messages, and for parallel mesages
        # they will pick-up messages from queues
        msg_thread_count = int(self.config.get("msg_threads", 4))
        mod_thread_count = int(self.config.get("mod_threads", 4))

        self.msg_processors["general"] = [threading.Thread(target=self.process_message_general)
                                          for x in range(msg_thread_count)]
        self.msg_processors["parallel"] = [threading.Thread(target=self.process_message_parallel)
                                           for x in range(mod_thread_count)]
        # lauch this threads
        [t.start() for t in self.msg_processors["general"]]
        [t.start() for t in self.msg_processors["parallel"]]

        logger.info("Multithreading intialized: {}x{} grid.".format(
            msg_thread_count, mod_thread_count))

    def __init__(self, config, testmode=False, onlyforuid=None):
        self.config = config
        if onlyforuid:
            onlyforuid = int(onlyforuid)
        self.onlyforuid = onlyforuid
        self.testmode = testmode

        self.init_globals()
        self.init_vk_session()
        self.init_modules()

        self.init_multithreading()
        logger.info("All intializing complete")

    def poll_messages(self, queue):
        result = []
        for event in self.longpoll.listen():
            if event.type == VkBotEventType.MESSAGE_NEW:
                print("dispatching message ", event.object)
                queue.put(event.object)

    def process_message(self, msg):
        # global modes cant stop the message, i think

        logger.info("New message! {}".format(msg.text))

        self.process_message_global(msg)

        logger.debug("Sending messages to general queue")

        self.msg_queue["general"].put(msg)

    def process_message_global(self, message):
        try:
            for mod in self.modules["global"]:
                self.process_message_in_module(mod, message)
        except:
            logger.exception("Error in global modules processing")

    def process_message_in_module(self, module, message):

        # because VK want only user_id or chat_id, and chat_id in priority
        if message.peer_id > 2000000000:
            chatid = message.peer_id
        else:
            chatid = None

        userid = None

        if not chatid:
            userid = message.from_id

        return module.process_message(message, chatid, userid)

    # general processing thread: picks messages from general queue

    def process_message_general(self):

        def process_in_unique_modules(message):
            for m in self.modules["unique"]:
                if self.process_message_in_module(m, message) == True:
                    logger.info("Unique module {} worked".format(m.__class__))
                    return True
            return False

        while True:
            try:
                message = self.msg_queue["general"].get()

                # if one of the uniq modules returned true, do not process
                # message next
                if process_in_unique_modules(message):
                    # pick new message
                    continue

                logger.info("Sending message to parallel modules")
                # multiply message in count of parallel module.
                # processor will take it and use corresponding module
                # cant pass in it the module itself, because thread obj cant be
                # pickled
                for i, _ in enumerate(self.modules["parallel"]):
                    self.msg_queue["parallel"].put((message, i))
            except:
                logger.exception("Processing in general failed")

    def process_message_parallel(self):
        while True:
            try:
                message, module_index = self.msg_queue["parallel"].get()
                logger.debug("Parallel message processing in {}"
                             .format(self.modules["parallel"][module_index].__class__))

                self.process_message_in_module(
                    self.modules["parallel"][module_index], message)
            except:
                logger.exception("Processing in parallel failed")

    # shorcuts for common-use vk-api requests
    def send_message(self, text="", chatid=None, userid=None, attachments=None, send_sticker=False):
        if self.testmode:
            print("----", text, attachments)
            return

        if not attachments:
            attachments = {}

        op = self.api.messages.send

        # change some cirillic to latin
        # for not to triger another tulen
        text = text.replace(u"а", u"a")
        text = text.replace(u"е", u"e")
        text = text.replace(u"о", u"o")
        text = text.replace(u"с", u"c")

        # to send message for username, not userid
        args = {"peer_id": chatid or userid, "message": text, "attachment": attachments,
                "random_id": random.randint(0xfff, 0xffffff)}

        if send_sticker:
            args["sticker_id"] = random.randint(1, 168)

        ret = vkrequest.perform(op, args)

        if not ret:
            logger.warning("No answer for send message request")

        logger.info("Sent message to c[{}]:u[{}] with attachment [{}]".format(chatid,
                                                                              userid,
                                                                              repr(attachments)))

        logger.info("response is {}".format(repr(ret)))
        return ret

    def get_all_friends(self, fields):
        operation = self.api.friends.get
        args = {"fields": fields}
        ret = vkrequest.perform(operation, args)
        logger.info("Got friends")
        return ret

    def __upload_images_vk(self, files):
        photos = []
        upload = vk_api.VkUpload(self.vk_session)
        attachments = []
        photos = upload.photo_messages(photos=files)  # [0]
        for f in photos:
            attachments.append(
                'photo{}_{}'.format(f['owner_id'], f['id'])
            )

        return attachments

    def upload_images_files(self, files):
        logger.info("Uploading message images...")

        attc = self.__upload_images_vk(files)

        return attc

    def find_video(self, req):
        op = self.api.video.search
        args = {"q": req, "adult": 0, "search_own": 0, "count": 1}
        resp = vkrequest.perform(op, args)
        try:
            video = resp["items"][0]
            r = "video" + str(video["owner_id"]) + "_" + str(video["id"])
            return [r, ]
        except:
            logger.exception("Video search failed")
            return None

    def find_doc(self, req):

        op = self.api.docs.search
        args = {"q": req, "count": 1}
        resp = vkrequest.perform(op, args)
        try:
            doc = resp["items"][0]
            r = "doc" + str(doc["owner_id"]) + "_" + str(doc["id"])
            return [r, ]
        except:
            logger.exception("Document logging failed")
            return None

    def find_wall(self, req):
        # log.info("Looking for wall post")
        op = self.api.newsfeed.search
        args = {"q": req, "count": 1}
        resp = vkrequest.perform(op, args)
        try:
            wall = resp["items"][0]
            r = "wall" + str(wall["owner_id"]) + "_" + str(wall["id"])
            return [r, ]
        except:
            logger.exception("Wall post search failed")
            return None

    def get_news(self, count=10):
        logger.info("Gathering newsfeed")
        op = self.api.newsfeed.get
        args = {"filters": "post", "count": count}
        resp = vkrequest.perform(op, args)
        return resp["items"]

    def like_post(self, post_id, owner_id):
        logger.info("Liking post")
        op = self.api.likes.add
        args = {"type": "post", "item_id": post_id, "owner_id": owner_id}
        resp = vkrequest.perform(op, args)

    def friendStatus(self, user_ids):
        logger.info("Getting friend status")
        op = self.api.friends.areFriends
        args = {"user_ids": user_ids}
        resp = vkrequest.perform(op, args)
        return resp

    def getUser(self, userid, fields, name_case):
        logger.info("Getting user information")
        op = self.api.users.get
        args = {"user_ids": userid, "fields": fields, "name_case": name_case}
        resp = vkrequest.perform(op, args)
        return resp[0]

    def friendAdd(self, user_id):
        logger.info("Adding to friends")
        op = self.api.friends.add
        args = {"user_id": user_id}
        resp = vkrequest.perform(op, args)
        return True

    def getRequests(self):
        logger.info("Getting  friends requests")
        op = self.api.friends.getRequests
        args = {}
        resp = vkrequest.perform(op, args)
        return resp["items"]
