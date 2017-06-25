#!/usr/bin/python
# -*- coding: utf-8 -*-

import random
# from io import StringIO
import io

import requests
from PIL import Image
import traceback
import numpy


# logger = logging.getLogger("tulen.pixelsort")


def glitch_an_image(local_image):
    files = {'image': open(local_image, 'rb')}
    data = {'method': 'grey',
            'columns': 'on',
            'threshold': random.randint(30, 100)}

    r = requests.post("http://pixelsort.glitch.me/", files=files, data=data)

    if r.status_code == 200:
        with open(local_image, 'wb') as f:
            for chunk in r:
                f.write(chunk)
    print("Glitched image")


class Processor:
    def __init__(self, vkuser):
        self.user = vkuser

    def process_message(self, message, chatid, userid):
        print("pixelsort, process_message")

        message_body = message["body"].lower()
        try:
            photo_url = message["attachments"][0]["photo"]["photo_604"]
            r = requests.get(photo_url)
            i = Image.open(io.BytesIO(r.content))
        except Exception as e:
            print("pixelsort, exception: {}".format(e))
            return

        if message_body == u"сортани":
            i.save("./files/neg.jpg")
            glitch_an_image("./files/neg.jpg")
            a = u"Сортанул"
        else:
            return

        print('pixelsort, sorted, attaching image to message')

        msg_attachments = self.user.upload_images_files(["./files/neg.jpg", ])

        if not msg_attachments:
            return

        self.user.send_message(text=a, attachments=msg_attachments, chatid=chatid, userid=userid)

        # print('pixelsort, attached message with image')
        #
        # wall_attachments = self.user.upload_images_files_wall(["./files/neg.jpg", ])
        # if not wall_attachments:
        #    print("Error in wall attachments")
        #    return
        # self.user.post(a, attachments = wall_attachments, chatid = chatid, userid=userid)


if __name__ == '__main__':
    import sys

    im = sys.argv[1]

    glitch_an_image(im)
