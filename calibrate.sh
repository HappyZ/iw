#!/bin/bash

for i in `seq 1 1000`; do
	sudo /usr/sbin/iw wlp58s0 measurement ftm_request config_entry | tail -n +3 >> result_$1
	sleep 0.01
done
