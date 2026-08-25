# Release closure files

`<version>.env` is the complete, authoritative coordinated release closure.
It is the only file whose values are embedded in a release image.

`<version>.requirements` records exact decisions made before the rest of a
release closure can be finalized. Every key in it must also appear with the
same value in `<version>.env`. The ISO manifest loader and the installed
closure selector both enforce that equality; requirements never override or
silently supply a missing manifest value.

This separation lets a release policy be locked while component commit pins
are still moving, without publishing a misleading, incomplete release
manifest.

Beginning with 0.2.1, the closure also carries five repository-root tuples:
`KILIX_SYSTEM_MONITOR`, `KILIX_DESKTOP_SDK`, `KILIX_ICEWM`,
`KILIX_MEDIA_SDK`, and `KILIX_WAYDROID`. Each tuple has an exact 40-character
`_REF`, its canonical HTTPS `_REPO`, and a declared-empty `_BRANCH`. Component
versions and child gitlink SHAs are not duplicated here; they are verified from
the manifests and Git trees selected by those root commits.
