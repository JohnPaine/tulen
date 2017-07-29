

class Processor:
    def __init__(self, user):
        self.user = user


    def process_message(self, message, chatid, userid):
        message_body = message["body"].lower()
        if self.is_request(message_body):
            self.user.send_message(hlp, chatid=chatid, userid=userid)