#!/bin/bash
cd ./SSF2-linux/data/
cp  SSF2.swf run
cd ../../
python GameDataAPI.py &
cd SSF2-linux/
./SSF2
