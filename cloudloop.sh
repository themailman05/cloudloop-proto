#/bin/bash

jackd -d alsa -r 44100 & sleep 2; qjackctl
