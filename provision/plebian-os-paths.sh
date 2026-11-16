# Plebian-OS installed paths.
#
# This is the one definition of where the files of this repository live on an
# installed system. Scripts that are deployed as single files cannot source it
# at run time, so each carries a verbatim copy of the block between the two
# marker lines, and tests/test_installed_paths.py holds every copy equal to
# this one. Python helpers carry the same names as module constants, held
# equal by the same test.
#
# The values are fixed on purpose. A root helper must not take its install
# locations from the caller's environment.

# >>> plebian-os-paths
PLEBIAN_OS_SBINDIR=/usr/sbin
PLEBIAN_OS_BINDIR=/usr/bin
PLEBIAN_OS_LIBEXECDIR=/usr/libexec/plebian-os
PLEBIAN_OS_LIBDIR=/usr/lib/plebian-os
PLEBIAN_OS_DATADIR=/usr/share/plebian-os
PLEBIAN_OS_NOTICEDIR=/usr/share/plebian-os/notices
PLEBIAN_OS_PAYLOADDIR=/var/lib/plebian-os/payloads
PLEBIAN_OS_UNITDIR=/usr/lib/systemd/system
# <<< plebian-os-paths
