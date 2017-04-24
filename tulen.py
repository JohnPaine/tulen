#!/usr/bin/python
# -*- coding: utf-8 -*-

from vkuser import VkUser
import sys
import traceback
import io
from optparse import OptionParser
import yaml
import logging
import logging.config
import utils

LOG_SETTINGS = {
    'version': 1,
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'level': 'INFO',
            'formatter': 'default',
            'stream': 'ext://sys.stdout',
        },
    },
    'formatters': {
        'default': {
            '()': 'multiline_formatter.formatter.MultilineMessagesFormatter',
            'format': '[%(levelname)s] %(message)s'
        },
    },
    'loggers': {
        'tulen': {
            'level': 'DEBUG',
            'handlers': ['console', ]
        },
    }
}

logging.config.dictConfig(LOG_SETTINGS)
logger = logging.getLogger("tulen")


def run_processing(vkuser):
    def process_messages(vkuser):
        try:
            msg = vkuser.poll_messages()
            vkuser.process_messages(msg)
        except:
            logger.exception("Something wrong while processing dialogs")
            if vkuser.testmode:
                return False

        return True

    while process_messages(vkuser):
        pass


def prepareUser(config, testmode, only_for_uid):
    vkuser = VkUser(config, testmode, only_for_uid)

    logger.info("Created user api")
    logger.info("Starting processing... ")

    return vkuser


def main():
    parser = OptionParser()
    parser.add_option("-c", "--config", dest="config",
                      help="configuration file to use", default="access.yaml", metavar="FILE.yaml")
    parser.add_option("-t", "--test", dest="test_mode",
                      help="test mode", action="store_true", default=False)

    parser.add_option("-o", "--only_for_uid", dest="only_for_uid",
                      help="work only with master's messages")

    (options, args) = parser.parse_args()

    logger.info("*************Tulen vk.com bot****************")

    config = utils.load_yaml(options.config)

    logger.info("Loaded configuration ")
    logger.info(yaml.dump(config))
    user = prepareUser(config, options.testmode, options.only_for_uid)
    run_processing(user)


if __name__ == '__main__':
    main()
