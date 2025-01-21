#!/bin/bash
cd `dirname "$0"`

# pack
cd a-cleartext
for i in * ; do betacrush.py mem "$i" ../b-betacrushed-mem/"$i" ; done
for i in * ; do betacrush.py sfx "$i" ../b-betacrushed-sfx/"$i" ; done
for i in * ; do knirsch.py pack "$i" ../b-knirsched/"$i" ; done
cd -
# unpack
cd b-betacrushed-sfx
# ...this will fail for some (small) files because the non-packed version was copied.
for i in * ; do betacrush.py unpack "$i" ../c-unbetacrushed/"$i" ; done
cd -
cd b-knirsched
for i in * ; do knirsch.py unpack "$i" ../c-unknirsched/"$i" ; done
cd -
# check packed files
echo "Checking packed files:"
diff -q b-betacrushed-mem expected-betacrushed-mem
diff -q b-betacrushed-sfx expected-betacrushed-sfx
diff -q b-knirsched expected-knirsched
# check unpacked files
echo "Checking unpacked files:"
#	22.prg 71.prg 7f.prg 7g.prg 80.prg 81.prg 82.prg 83.prg
#	were copied manually to target, see comment above
#	(could not be unpacked because they were never packed)
diff -q a-cleartext c-unbetacrushed
diff -q a-cleartext c-unknirsched
echo "Done."
