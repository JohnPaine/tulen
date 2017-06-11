import logging
import multiprocessing
import os
import tempfile
import threading
import time
import urllib.request as url_request
# from urllib3 import request
from datetime import datetime

import psutil
from twocaptchaapi import TwoCaptchaApi, Captcha
from vk.exceptions import VkAPIError

import utils

logger = logging.getLogger("seal")


class Captcha2Captcha:
    def __init__(self, key):
        self.api = TwoCaptchaApi(key)
        self.last_captcha = None

    def solve(self, filename):
        with open(filename, 'rb') as captcha_file:
            _captcha = self.api.solve(captcha_file)
            res = _captcha.await_result()
            self.last_captcha = _captcha
            return res

    def balance(self):
        return self.api.get_balance()

    @staticmethod
    def report_bad():
        if captcha:
            Captcha.report_bad()


captcha = None


def init_captcha(service, cred):
    global captcha
    captcha = {"2captcha": Captcha2Captcha}[service](cred)


# used to trigger the permission for request processing
RATED_LOCK = multiprocessing.Lock()

# used for messaging obout the state of operation: can do new, or can't
RATED_QUEUE = multiprocessing.Queue()

# used to sincronize multithreading method-info writing
JSON_LOCK = multiprocessing.Lock()

# special event for all threads about absence of captcha
# and that it should not wait for it is solved
CAPTHCA_FREE = multiprocessing.Event()
CAPTHCA_FREE.set()


# rate-limit decorator, but works only in one thread
def RateLimited(maxPerSecond):
    minInterval = 1.0 / float(maxPerSecond)

    def decorate(func):
        lastTimeCalled = [0.0]

        def rateLimitedFunction(*args, **kargs):
            elapsed = time.clock() - lastTimeCalled[0]
            leftToWait = minInterval - elapsed
            if leftToWait > 0:
                time.sleep(leftToWait)
            ret = func(*args, **kargs)
            lastTimeCalled[0] = time.clock()
            return ret

        return rateLimitedFunction

    return decorate


def run_ratelimit_dispatcher():
    # yes, it's a process. we need a process to avoid interference with main process.
    p = multiprocessing.Process(target=rl_dispatch)
    p.daemon = True
    p.start()
    logger.info("Rate-limit dispatcher started")
    return p


# this method can be trigerred only N times per second. (per thread/process)
@RateLimited(2.5)
def set_event():
    try:
        RATED_LOCK.release()
    except ValueError:
        pass


# to synchronize set_event between threads/processes we use event queue.
# when there is a message in queue, it means that PERFORM method was invoked and it locked the rated_lock.
# so we can try to unlock it, if rate_limit decorator allows.
def rl_dispatch():
    set_event()
    while True:
        RATED_QUEUE.get()
        set_event()


manager = multiprocessing.Manager()
mmap = manager.dict({})


def update_minfo(method, type, incr):
    if not hasattr(method, '_method_name'):
        return

    method_name = method._method_name
    with JSON_LOCK:
        json_obj = utils.load_json("./files/minfo.json")
        if not json_obj:
            json_obj = {"method": {"type": incr}}
        else:
            mmap = json_obj.get(method_name, {})
            mmap[type] = mmap.get(type, 0) + incr
            json_obj[method_name] = mmap
        to_write = utils.pretty_dump(json_obj)
        open("./files/minfo.json", "wb").write(to_write)


def info_string(method, val):
    process = psutil.Process(os.getpid())
    return datetime.now().strftime('%H:%M:%S') + "\t" + str(method) + "\t" + str(
        process.memory_info().rss / 1024.0 / 1024.0) + "\t" + str(val) + "\t" + "\t" + str(threading.active_count()) + "\n"


def perform_now(operation, args):
    ret = operation(**args)
    update_minfo(operation, "success", 1)
    return ret


def perform(operation, args):
    RATED_LOCK.acquire()
    RATED_QUEUE.put("Can unlock")

    # means THIS thread is solving captcha
    this_captcha = False

    # means repeat sending if something failed
    send = True

    captcha_fails = 0

    process = psutil.Process(os.getpid())

    def process_capthca():
        # TODO: change!!!
        # global capthca solver
        # if not capthca:
        #     raise
        # if this_captcha:
        Captcha2Captcha.report_bad()

        CAPTHCA_FREE.clear()

        temp_name = next(tempfile._get_candidate_names())
        temp_name = "./files/{}.jpg".format(temp_name)
        url_request.urlretrieve(e.captcha_img, temp_name)

        try:
            res = captcha.solve(temp_name)
        except:
            res = None
            logger.exception("Something bad in captcha solving")

        return res

    with open("api_history", "a") as file:
        while send:
            try:
                logger.info("{} {}mb {} active threads"
                            .format(operation,
                                    process.memory_info().rss / 1024.0 / 1024.0,
                                    threading.active_count()))

                if not this_captcha and not CAPTHCA_FREE.is_set():  # captcha in progress, wait
                    logger.info("Waiting for captcha solve in other thread")
                    CAPTHCA_FREE.wait()

                ret = operation(**args)
                update_minfo(operation, "success", 1)

                # on prev iteration solved capcha, it is in args
                if args.get("captcha_key", None):
                    update_minfo(operation, "capthca_ok", 1)
                    # TODO: change!!!
                    file.write(info_string(operation,
                                           "CAPTCHA OK [{}]; balance [{}]".format(args.get("captcha_key", None),
                                                                                  TwoCaptchaApi.get_balance())))
                else:
                    file.write(info_string(operation, "OK"))

                # inform other threads that they can continue
                CAPTHCA_FREE.set()
                return ret

            except VkAPIError as e:
                # capthca needed
                if e.code == 14:

                    res = process_capthca()
                    this_captcha = True

                    if res:
                        # TODO: change!!!
                        update_minfo(operation, "captcha", 1)
                        args.update({"captcha_sid": e.captcha_sid, "captcha_key": res})
                    else:
                        captcha_fails += 1

                elif e.code == 6:
                    logger.warning("**** To many req for sec, throttling")
                    time.sleep(1)
                    update_minfo(operation, "throttle", 1)
                    file.write(info_string(operation.method, "THROTTLE"))

                else:
                    update_minfo(operation, "error", 1)
                    file.write(info_string(operation.method, str(e)))
                    CAPTHCA_FREE.set()
                    raise

            if captcha_fails > 5:
                send = False
