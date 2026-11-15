#!/usr/bin/python3
"""Stage nothing for the Kilix Ask command model: it is a first-use download.

From Plebian-OS 0.2.3 the LFM2 command model (provision/command-model.json)
is not on the installation media and no upgrade downloads or stages it. Kilix
Ask uses its grammar until the model is installed, and offers the download on
the first interactive `kilix ask` and on the Kilix model wizard's Local
Workflows / Kilix Ask page. A machine that already has delivery v9 gets the
current delivery from those files in the desktop user's step
(install-image-models.py), without a download.

This file stays because an updater from an earlier release candidate runs it,
as root, from the new checkout, and stops its upgrade if it fails. It checks
the pin, accepts the arguments earlier callers pass, and changes nothing. It
never opens the network and never writes, so an archive an earlier release
staged under /usr/local/share/kilix/model-archives, and the licence documents
it put under /usr/local/share/doc/plebian-os/models, stay as they are.
"""
import argparse
import json
from pathlib import Path
import re


def check_pin(pin):
    delivery = pin.get('delivery') or {}
    if (pin.get('schema') != 'plebian-os.command-model-archive/v2'
            or pin.get('asset_id') != 'lfm2-kilix-commands'
            or not re.fullmatch(r'[0-9a-f]{64}', pin.get('sha256', ''))
            or not re.fullmatch(r'[a-zA-Z0-9._-]+', pin.get('version', ''))
            or delivery.get('mode') != 'first-use-download'
            or delivery.get('on_installation_media') is not False
            or delivery.get('staged_by_upgrade') is not False):
        raise ValueError('invalid command model pin')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    # Accepted and ignored: the arguments earlier provisioners and updaters pass.
    parser.add_argument('--archive', type=Path, help=argparse.SUPPRESS)
    parser.add_argument('--cache-dir', type=Path, help=argparse.SUPPRESS)
    parser.add_argument('--documents-dir', type=Path, help=argparse.SUPPRESS)
    parser.add_argument('--offline', action='store_true', help=argparse.SUPPRESS)
    parser.add_argument('--verify-only', action='store_true', help=argparse.SUPPRESS)
    parser.parse_args(argv)
    pin = json.loads(Path(__file__).with_name('command-model.json').read_text())
    check_pin(pin)
    print('Command model ' + pin['version'] + ' is a first-use download; nothing was staged. '
          'Kilix Ask offers it on first use.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
