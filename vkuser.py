# coding: utf-8
import json
import logging
import multiprocessing
import os
import random
import sys
import threading
import time
import traceback
import io

import requests
import vk
from PIL import Image

import vkrequest
from modules import pixelsort
from seal_management import SealMode

sys.path.append("./modules")
logger = logging.getLogger('seal')
logger.setLevel(logging.DEBUG)

vk_script_getmsg = """var k = 200;
var messages = API.messages.get({"count": k});

var ids = "";
var a = k;  
while (a >= 0) 
{ 
ids=ids+messages["items"][a]["id"]+",";
a = a-1;
}; 
ids = ids.substr(0,ids.length-1);
API.messages.markAsRead({"message_ids":ids});

return messages;"""


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
            logger.warning("Anti-captcha cant be initialized: no config")
        else:
            service = captcha_config["service"]
            creds = captcha_config["credentials"]
            vkrequest.init_captcha(service, creds)
            logger.info("Captcha [{}] initialized. balance: {}".format(service,
                                                                       vkrequest.captcha.balance()))

        # enable rate limiting
        self.rate_limit_dispatch_process = vkrequest.run_ratelimit_dispatcher()

        logger.info("Global systems initialized")

    def init_vk_session(self):
        if self.test_mode and self.run_mode != SealMode.Breeder:
            self.api = None
            logger.info("VK Session: test mode")
        else:
            session = vk.Session(access_token=self.config["access_token"]["value"])

            timeout = self.config["access_token"].get("connection_timeout", 10)
            self.my_uid = self.config["access_token"]["user_id"]
            if not self.my_uid:
                raise RuntimeError("Access config: user_id not defined")

            self.api = vk.API(session, v='5.50', timeout=timeout)

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
        def add_module(modif, modproc):
            modules = self.modules.get(modif, [])
            modules.append(modproc)
            self.modules[modif] = modules

        for module in mod_list:
            data = module.split()
            modifier = "parallel"
            module = data[0]
            if len(data) > 1:
                modifier = data[0]
                module = data[1]

            package = __import__("modules" + "." + module)
            processor = getattr(package, module)
            modprocessor = processor.Processor(self)

            add_module(modifier, modprocessor)

            logger.info("Loaded module: [{}] as {}".format(
                "modules" + "." + module, modifier))

    def init_multithreading(self):
        # create message queue: general (first step for uniq modules)
        self.msg_queue["general"] = multiprocessing.Queue()
        # create message queues: paralel (for parallel message processing)
        self.msg_queue["parallel"] = multiprocessing.Queue()

        # create threads for general messages, and for parallel mesages
        # they will pick-up messages from queues
        msg_thread_count = int(self.config.get("msg_threads", 4))
        mod_thread_count = int(self.config.get("mod_threads", 4))

        self.msg_processors["general"] = [threading.Thread(target=self.process_message_general, daemon=True)
                                          for x in range(msg_thread_count)]
        self.msg_processors["parallel"] = [threading.Thread(target=self.process_message_parallel, daemon=True)
                                           for x in range(mod_thread_count)]
        # launch these threads
        [t.start() for t in self.msg_processors["general"]]
        [t.start() for t in self.msg_processors["parallel"]]

        logger.info("Multithreading initialized: {}x{} grid.".format(
            msg_thread_count, mod_thread_count))

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.rate_limit_dispatch_process:
            print('Exiting vk_user instance - calling self.rate_limit_dispatch_process.terminate()')
            self.rate_limit_dispatch_process.terminate()
            self.rate_limit_dispatch_process.join(5)
        for thread in self.msg_processors['general']:
            thread.do_run = False
            thread.join(5)
        for thread in self.msg_processors['parallel']:
            thread.do_run = False
            thread.join(5)

    def __init__(self, config, test_mode, run_mode, only_for_uid):
        self.modules = {"global": [], "unique": [], "parallel": []}
        self.msg_processors = {}
        self.msg_queue = {}
        self.rate_limit_dispatch_process = None
        self.action_stats = {}

        self.config = config
        if only_for_uid:
            only_for_uid = int(only_for_uid)
        self.only_for_uid = only_for_uid
        self.test_mode = test_mode
        self.run_mode = run_mode

        self.init_globals()
        self.init_vk_session()
        self.init_modules()

        self.init_multithreading()
        logger.info("All intializing complete")

    def poll_messages(self):
        if self.test_mode and self.run_mode != SealMode.Breeder:
            msg = input("msg>> ")
            messages = [
                {"read_state": 0, "id": "0", "body": msg, "chat_id": 2}]
        else:
            operation = self.api.execute
            args = {"code": vk_script_getmsg}
            ret = vkrequest.perform(operation, args)
            messages = ret["items"]

        return messages

    def process_messages(self, messages):
        unread_messages = [msg for msg in messages if msg["read_state"] == 0]

        # filter messages if they are for specified uid
        if self.only_for_uid:
            unread_messages = [msg for msg in unread_messages if msg[
                "user_id"] == self.only_for_uid]

        if len(unread_messages) > 0:
            logger.info("Unread messages: {}".format(len(unread_messages)))

            # global modes cant stop the message, i think
            for m in unread_messages:
                self.process_message_global(m)

            logger.debug("Sending messages to general queue [{}]".format(len(unread_messages)))

            [self.msg_queue["general"].put(message) for message in unread_messages]

    def process_message_global(self, message):
        try:
            print("process_message_global, message: {}".format(message))
            for mod in self.modules["global"]:
                print('\tprocess message in module: {}'.format(mod))
                self.process_message_in_module(mod, message)
        except:
            logger.exception("Error in global modules processing")

    def process_message_in_module(self, module, message):
        # because VK wants only user_id or chat_id, and chat_id in priority
        print("process_message_in_module, module: {}, message: {}".format(module, message))
        chat_id = message.get("chat_id", None)
        user_id = None

        if not chat_id:
            user_id = message.get("user_id", None)

        return module.process_message(message, chat_id, user_id)

    # general processing thread: picks messages from general queue

    def process_message_general(self):

        def process_in_unique_modules(message):
            for m in self.modules["unique"]:
                if self.process_message_in_module(m, message):
                    logger.info("Unique module {} worked".format(m.__class__))
                    return True
            return False

        t = threading.currentThread()

        while getattr(t, "do_run", True):
            try:
                message = self.msg_queue["general"].get()

                # if one of the unique modules returned true, do not process
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
        t = threading.currentThread()

        while getattr(t, "do_run", True):
            try:
                message, module_index = self.msg_queue["parallel"].get()
                logger.debug("Parallel message processing in {}"
                             .format(self.modules["parallel"][module_index].__class__))

                self.process_message_in_module(self.modules["parallel"][module_index], message)
            except:
                logger.exception("Processing in parallel failed")

    # shortcuts for common-use vk-api requests
    @SealMode.collect_vk_user_action_stats
    @SealMode.mark_action_load_balancing
    def send_message(self, text="", chatid=None, userid=None, attachments=None):
        if self.test_mode:
            print("test mode, printing message ---->> ", text, attachments)
            return

        if not text and not attachments:
            logger.critical('VK_API: cannot send empty message without attachments!')
            return None

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
        args = {"chat_id": chatid, "message": text, "attachment": attachments,
                "random_id": random.randint(0xfff, 0xffffff)}

        if isinstance(userid, int):
            args.update({"user_id": userid})
        else:
            args.update({"domain": userid})

        ret = vkrequest.perform(op, args)

        if not ret:
            logger.warning("No answer for send message request")

        logger.info("Sent message to c[{}]:u[{}] with attachment [{}]".format(chatid,
                                                                              userid,
                                                                              repr(attachments)))

        logger.info("response is {}".format(repr(ret)))
        return ret

    def get_friends(self, fields=None, user_id=None, order='name', count=None, offset=None):
        operation = self.api.friends.get
        args = {"fields": fields, "order": order, "count": count, "offset": offset, "user_id": user_id}
        ret = vkrequest.perform(operation, args)
        logger.info("Got friends: {}".format(ret))
        return ret

    @SealMode.collect_vk_user_action_stats
    @SealMode.mark_action_load_balancing
    def send_sticker(self, user_id, peer_id, chat_id, sticker_id=0):
        op = self.api.messages.sendSticker

        args = {"peer_id": peer_id, "chat_id": chat_id,
                "random_id": random.randint(0xfff, 0xffffff),
                "sticker_id": random.randint(1, 168) if sticker_id == 0 else sticker_id}

        if isinstance(user_id, int):
            args.update({"user_id": user_id})
        else:
            args.update({"domain": user_id})

        ret = vkrequest.perform(op, args)

        # wtf??? - if send_sticker error (e.g. sticker missing) - trying again
        if ret == 100 or (900 <= ret <= 902):
            logger.warning("Sent sticker response is {}".format(repr(ret)))
            args["random_id"] = random.randint(0xfff, 0xffffff)
            args["sticker_id"] = random.randint(1, 168)
            ret = vkrequest.perform(op, args)

        logger.info("Sent sticker")
        return ret

    @SealMode.collect_vk_user_action_stats
    @SealMode.mark_action_load_balancing
    def post(self, text, chatid, userid, attachments):

        op_post = self.api.wall.post
        args = {"owner_id": self.my_uid, "message": text,
                "attachments": ",".join(attachments)}

        ret = vkrequest.perform(op_post, args)
        logger.info("Wall post created")

        return ret

    def __upload_images_vk(self, upserver, files):
        photos = []
        for f in files:
            op = requests.post
            filename = f.split("/")[-1]
            args = {"url": upserver["upload_url"], "files": {'photo': (filename, open(f, 'rb'))}}
            try:
                # i think we do not need to use rate-limit operation here
                response = vkrequest.perform_now(op, args)
                resp_json = json.loads(response.content.decode('utf-8'))
                ph = {"photo": resp_json["photo"],
                      "server": resp_json["server"],
                      "hash": resp_json["hash"]}
                photos.append(ph)
            except Exception as e:
                logger.exception("Upload images failed")
                print("Upload images failed, e: {}".format(e))

        return photos

    @SealMode.collect_vk_user_action_stats
    def upload_images_files(self, files):
        logger.info("Uploading message images...")
        op = self.api.photos.getMessagesUploadServer
        args = {}

        upserver = vkrequest.perform(op, args)
        ids = self.__upload_images_vk(upserver, files)
        logger.info("Uploaded message images")
        attachments = []

        for i in ids:
            try:
                op = self.api.photos.saveMessagesPhoto
                args = {"photo": i["photo"], "server": i[
                    "server"], "hash": i["hash"]}

                resp = vkrequest.perform(op, args)
                attachments.append(
                    "photo" + str(resp[0]["owner_id"]) + "_" + str(resp[0]["id"]))
            except Exception as e:
                logger.exception("Saving message image failed")
                return None

        return attachments

    @SealMode.collect_vk_user_action_stats
    def upload_images_files_wall(self, files):

        logger.info("Uploading wall images...")
        op = self.api.photos.getWallUploadServer
        args = {"group_id": self.my_uid}

        upserver = vkrequest.perform(op, args)

        photos = self.__upload_images_vk(upserver, files)
        logger.info("Uploaded wall images")
        ids = photos
        attachments = []
        for i in ids:
            try:
                op = self.api.photos.saveWallPhoto
                args = {"user_id": self.my_uid,
                        "group_id": self.my_uid,
                        "photo": i["photo"],
                        "server": i["server"],
                        "hash": i["hash"]}

                resp = vkrequest.perform(op, args)
                attachments.append(
                    "photo" + str(resp[0]["owner_id"]) + "_" + str(resp[0]["id"]))
            except Exception as e:
                traceback.print_exc()
                logger.exception("Saving wall image failed, e: {}".format(e))
                break

        return attachments

    @SealMode.collect_vk_user_action_stats
    @SealMode.mark_action_load_balancing
    def find_video(self, req):
        logger.info("Looking for requested video")
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

    @SealMode.collect_vk_user_action_stats
    @SealMode.mark_action_load_balancing
    def find_doc(self, req):
        logger.info("Looking for document")
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

    @SealMode.collect_vk_user_action_stats
    @SealMode.mark_action_load_balancing
    def find_wall(self, req):
        logger.info("Looking for a wall post")
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

    @SealMode.collect_vk_user_action_stats
    def get_news(self, count=10):
        logger.info("Gathering newsfeed")
        op = self.api.newsfeed.get
        args = {"filters": "post", "count": count}
        resp = vkrequest.perform(op, args)
        return resp["items"]

    @SealMode.collect_vk_user_action_stats
    def like_post(self, post_id, owner_id):
        logger.info("Liking post")
        op = self.api.likes.add
        args = {"type": "post", "item_id": post_id, "owner_id": owner_id}
        resp = vkrequest.perform(op, args)

    @SealMode.collect_vk_user_action_stats
    def friendStatus(self, user_ids):
        logger.info("Getting friend status")
        op = self.api.friends.areFriends
        args = {"user_ids": user_ids}
        resp = vkrequest.perform(op, args)
        return resp

    @SealMode.collect_vk_user_action_stats
    def getUser(self, userid, fields, name_case):
        logger.info("Getting user information")
        op = self.api.users.get
        args = {"user_ids": userid, "fields": fields, "name_case": name_case}
        resp = vkrequest.perform(op, args)
        return resp[0]

    @SealMode.collect_vk_user_action_stats
    def friendAdd(self, user_id):
        logger.info("Adding to friends uid: {}".format(user_id))
        op = self.api.friends.add
        args = {"user_id": user_id}
        resp = vkrequest.perform(op, args)
        print('friend Add response: {}'.format(resp))
        return True

    @SealMode.collect_vk_user_action_stats
    def getRequests(self):
        logger.info("Getting friends requests")
        op = self.api.friends.getRequests
        args = {}
        resp = vkrequest.perform(op, args)
        return resp["items"]

    @SealMode.collect_vk_user_action_stats
    def get_dialogs(self, offset=0, count=200):
        op = self.api.messages.getDialogs
        args = {"offset": offset, "count": count}
        resp = vkrequest.perform(op, args)

        items = list(resp['items'])

        if resp['count'] > offset + count:
            new_count = resp['count'] - (offset + count)
            offset = count
            print('get_dialogs, new_count: {}, new_offset: {}'.format(new_count, offset))
            items.append(self.get_dialogs(offset, new_count))

        return items

    @SealMode.collect_vk_user_action_stats
    def get_chats_data(self, chats_per_iter=100, start_from=1, chats_data=None) -> dict:
        """Return data for all user chats (dialogs with user_count > 2).
                
        :param chats_per_iter: each VkApi request brings chats_per_iter chats.
            If chat doesn't exist, admin_id will be 0.
            Default: 100
        :param start_from: chat ids obtained starting from this counter.
            Default: 1
        :param chats_data: chats_data dict
            Default: None        
        :return: chats_data dict of format: {user_chat_id: dict(chat_data)}
        """
        if not chats_data:
            chats_data = dict()

        try:
            chat_ids = list(str(i) for i in range(start_from, start_from + chats_per_iter))
            iter_chats_data = self.get_chat(chat_id='', chat_ids=chat_ids)

            for chat_data in iter_chats_data:
                print('\tget_chats_data, checking chat_data: {}'.format(chat_data))
                if chat_data['admin_id'] == 0:
                    print('\t\tstopping chat_data checks on empty admin_id.')
                    return chats_data

                chats_data[int(chat_data['id'])] = chat_data
            start_from += chats_per_iter

        except Exception as e:
            print('on_join_chat_cmd, exception occurred: {}'.format(e))
            traceback.print_exc()
            return chats_data

        return self.get_chats_data(chats_per_iter, start_from, chats_data)

    @SealMode.collect_vk_user_action_stats
    def add_chat_user(self, chat_id, user_id):
        print('VK_API: adding user:{} to chat_id:{}'.format(user_id, chat_id))

        op = self.api.messages.addChatUser
        args = {"chat_id": chat_id, "user_id": user_id}
        return vkrequest.perform(op, args)

    @SealMode.collect_vk_user_action_stats
    def remove_chat_user(self, chat_id, user_id):
        print('VK_API: removing user:{} from chat_id:{}'.format(user_id, chat_id))

        op = self.api.messages.removeChatUser
        args = {"chat_id": chat_id, "user_id": user_id}
        return vkrequest.perform(op, args)

    @SealMode.collect_vk_user_action_stats
    def get_chat(self, chat_id, chat_ids=None, fields=''):
        op = self.api.messages.getChat
        args = {"chat_id": chat_id, "chat_ids": chat_ids, "fields": fields}
        return vkrequest.perform(op, args)

    @SealMode.collect_vk_user_action_stats
    def get_chat_users(self, chat_id, chat_ids=None, fields=None):

        op = self.api.messages.getChatUsers
        args = {"chat_id": chat_id,
                "chat_ids": chat_ids,
                "fields": fields}
        resp = vkrequest.perform(op, args)

        print('get_chat_users response: {}'.format(resp))

        return resp

    @SealMode.collect_vk_user_action_stats
    def send_group_invitation(self, group_id, user_id):
        print('sending group invitation for group_id: {}, to user_id: {}'.format(group_id, user_id))

        op = self.api.groups.invite
        args = {"group_id": group_id,
                "user_id": user_id}
        resp = vkrequest.perform(op, args)

        print('send_group_invitation response: {}'.format(resp))

        return resp

    @SealMode.collect_vk_user_action_stats
    def get_group_members(self, group_id, sort='id_asc', offset=None, count=None, fields=None, filter=None):

        op = self.api.groups.getMembers
        args = {"group_id": group_id,
                "sort": sort,
                "offset": offset,
                "count": count,
                "fields": fields,
                "filter": filter}
        resp = vkrequest.perform(op, args)

        print('get_group_members response: {}'.format(resp))

        return resp

    @SealMode.collect_vk_user_action_stats
    def pixelsort_and_post_on_wall(self, user_id):
        user = self.getUser(user_id, "photo_max_orig", name_case="Nom")
        photo_url = user["photo_max_orig"]
        r = requests.get(photo_url)

        i = Image.open(io.BytesIO(r.content))
        img_file = "./files/friend{}.jpg".format(user_id)
        i.save(img_file)

        pixelsort.glitch_an_image(img_file)

        wall_attachments = self.upload_images_files_wall([img_file, ])
        self.post(u"Привет, {} {}".format(user["first_name"], user["last_name"]), attachments=wall_attachments,
                       chatid=None, userid=user_id)
