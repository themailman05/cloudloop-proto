#/bin/bash

sudo aptitude install libopusfile-dev opus-tools libopus-dev libortp-dev libclalsadrv-dev

if [[ -f /usr/lib/libopusfile.so ]]; then
  echo "opusfile installed."
  #TODO check other require
  git clone http://www.pogo.org.uk/~mark/trx.git
  cd trx
  make
  sudo make install
fi

echo `which opusenc`
echo "Done!"
