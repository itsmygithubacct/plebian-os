"""Select the coordinated source release exercised by checkout-based tests."""
from pathlib import Path


def source_release(root):
    version = (root / "VERSION").read_text().strip()
    manifest = (root / "releases" / f"{version}.env").read_text().splitlines()
    # Alpha media has Debian package pins. The last published source checkout
    # and its independent carrier reviews belong to the 0.2.3 release.
    return "0.2.3" if "PLEBIAN_OS_RELEASE_MODE=0" in manifest else version


if __name__ == "__main__":
    print(source_release(Path(__file__).resolve().parents[1]))
