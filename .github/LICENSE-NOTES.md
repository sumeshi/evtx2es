# Release license collection

The collector includes installed runtime license/NOTICE files and the build
Python's license. Development-only dependencies are excluded.

## evtx 0.11.1

The [release metadata](https://github.com/omerbenamram/pyevtx-rs/blob/2b82a8b4935588248b8b09af4c537f2e32112521/pyproject.toml) explicitly declares MIT.
The release repository tree and wheel contain no license text or copyright notice
(checked 2026-09-18). `LICENSES/evtx-0.11.1.txt` therefore supplies the standard
MIT text, upstream declaration, source and author attribution. Template copyright
placeholders remain unfilled; they are not presented as an upstream notice.

The collector uses this material only for evtx 0.11.1 when the installed
package has no license files. Installed license files take precedence. Other
missing licenses still produce an error. Embedded native dependencies are not
fully audited by this collector.
