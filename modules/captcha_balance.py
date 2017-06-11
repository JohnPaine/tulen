#!/usr/bin/python
# -*- coding: utf-8 -*-


import vkrequest


class Processor:
    def __init__(self, user):
        self.user = user

    def process_message(self, message, chatid, userid):
        if "captchabalance" in message["body"].lower():
            balance = vkrequest.captcha.balance()
            self.user.send_message(
                text=u"Баланс на каптчарешателе: {}$. В день решается около 300 каптч, 1000 каптч стоит 1$. "
                     u"На сколько этого хватит - посчитаете сами.".format(balance), chatid=chatid, userid=userid)
