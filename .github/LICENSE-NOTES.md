# Release license collection

The collector includes installed runtime license/NOTICE files and the build
Python's license. Development-only dependencies are excluded.

## evtx 0.13.1

The [tagged Python project metadata](https://github.com/omerbenamram/pyevtx-rs/blob/0fe74a28edaa5030ed06c4c0e0a9f7b5a33d301e/pyproject.toml) classifies the release as MIT. The same tag's [Cargo metadata](https://github.com/omerbenamram/pyevtx-rs/blob/0fe74a28edaa5030ed06c4c0e0a9f7b5a33d301e/Cargo.toml) declares the embedded Rust crate as MIT/Apache-2.0; this bundle supplies the MIT option. The tagged source tree and installed wheel contain no license text or copyright notice (checked 2026-10-12). `LICENSES/evtx-0.13.1.txt` therefore supplies the standard MIT text, upstream declaration, source and author attribution. Template copyright placeholders remain unfilled; author metadata is not treated as a copyright notice.

The collector uses this material only for evtx 0.13.1 when the installed
package has no license files. Installed license files take precedence. Other
missing licenses still produce an error. Embedded native dependencies are not
fully audited by this collector.
