#!/bin/bash

sudo killall -v python3
sudo ./reset_rabbitmq_queues.sh
sudo python3 seal_breeder.py