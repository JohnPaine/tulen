john@john-ubuntu-1604:~$ sudo rabbitmqctl stop_app
[sudo] password for john: 
Stopping node 'rabbit@john-ubuntu-1604' ...
john@john-ubuntu-1604:~$ sudo rabbitmqctl reset
Resetting node 'rabbit@john-ubuntu-1604' ...
john@john-ubuntu-1604:~$ sudo rabbitmqctl start_app
#!/bin/bash

sudo rabbitmqctl stop_app
sudo rabbitmqctl reset
sudo rabbitmqctl start_app