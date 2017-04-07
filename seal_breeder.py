#!/usr/bin/python
# -*- coding: utf-8 -*-

# import logging
import yaml
import argparse
import subprocess

# LOG_SETTINGS = {
#     'version': 1,
#     'handlers': {
#         'console': {
#             'class': 'logging.StreamHandler',
#             'level': 'INFO',
#             'formatter': 'default',
#             'stream': 'ext://sys.stdout',
#         },
#     },
#     'formatters': {
#         'default': {
#             '()': 'multiline_formatter.formatter.MultilineMessagesFormatter',
#             'format': '[%(levelname)s] %(message)s'
#         },
#     },
#     'loggers': {
#         'seal_breeder': {
#             'level': 'DEBUG',
#             'handlers': ['console', ]
#         },
#     }
# }
#
# logging.config.dictConfig(LOG_SETTINGS)
# logger = logging.getLogger("seal_breeder")


def process(config, test_mode):
    config_files = config['list_of_config_files']

    for config_file in config_files:
        subprocess.Popen(['python seal.py', '-c', config_file])


def main():
    parser = argparse.ArgumentParser(description='Seal breeder program')
    parser.add_argument('-c', '--config', dest='config', metavar='FILE.yaml',
                        help='configuration file to use', default='seal_breeder_default_config.yaml')
    parser.add_argument('-t', '--test', dest='test_mode', help="test mode", action="store_true", default=False)

    args = parser.parse_args()
    print("************* Seal breeder - vk.com bot manager ****************")

    config = yaml.load(open(args.config))

    print("Loaded configuration ")
    print(yaml.dump(config))

    process(config, args.test_mode)

if __name__ == '__main__':
    main()