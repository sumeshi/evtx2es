# evtx2es

[![MIT License](http://img.shields.io/badge/license-MIT-blue.svg?style=flat)](LICENSE)
[![PyPI Version](https://img.shields.io/pypi/v/evtx2es)](https://pypi.org/project/evtx2es/)

![evtx2es logo](https://gist.githubusercontent.com/sumeshi/c2f430d352ae763273faadf9616a29e5/raw/1bf24feb55571bf7f0c7d8d4cb04bd0a511120f2/evtx2es.svg)

A command-line tool and Python library for parsing Windows Event Logs and importing the results into Elasticsearch.

Life is too short to process **huge Windows Event Logs** using **pure Python**.  
**evtx2es** leverages the Rust-based parser [pyevtx-rs](https://github.com/omerbenamram/pyevtx-rs), making it significantly faster than traditional tools.
It can also recover as many records as possible from corrupted, partially overwritten, or carved `.evtx` files.


## Usage

**evtx2es** can be used as a standalone command-line tool or integrated directly into your Python scripts.

```bash
$ evtx2es /path/to/your/file.evtx
```

```python
from evtx2es import evtx2es

evtx2es('/path/to/your/file.evtx')
```


### Arguments

**evtx2es** can process multiple files at once:

```bash
$ evtx2es file1.evtx file2.evtx file3.evtx
```

evtx2es can recursively process all `.evtx` files under a specified directory:

```bash
$ tree .
evtxfiles/
  ├── file1.evtx
  ├── file2.evtx
  ├── file3.evtx
  └── subdirectory/
    ├── file4.evtx
    └── subsubdirectory/
      ├── file5.evtx
      └── file6.evtx

$ evtx2es /evtxfiles/ # This recursively processes file1 through file6.
```


### Options

```
--version, -v

--help, -h

--quiet, -q
  Suppress standard output
  (default: False)

--multiprocess, -m:
  Enable multiprocessing for faster execution
  (default: False)

--size:
  Number of records to process per chunk (default: 500)

--host:
  Elasticsearch host address (default: localhost)

--port:
  Elasticsearch port number (default: 9200)

--index:
  Destination index name (default: evtx2es)

--scheme:
  Protocol scheme to use (http or https) (default: http)

--pipeline:
  Elasticsearch Ingest Pipeline to use (default: )

--datasetdate:
  Date of the latest record in the dataset, extracted from the `TimeCreated` field (MM/DD/YYYY.HH:MM:SS). If omitted, timestamps are not shifted.

--login:
  Username for Elasticsearch authentication

--pwd:
  Password for Elasticsearch authentication

--no-verify-certs:
  Disable TLS certificate verification for Elasticsearch connections (default: False)
```


### Examples

When using from the command line:

```bash
$ evtx2es /path/to/your/file.evtx --host=localhost --port=9200 --index=foobar --size=500
```

When using from a Python script:

```py
evtx2es("/path/to/your/file.evtx", host="localhost", port=9200, index="foobar", chunk_size=500)
```

With credentials for Elastic Security:

```bash
$ evtx2es /path/to/your/file.evtx --host=localhost --port=9200 --index=foobar --login=elastic --pwd=******
```

> [!WARNING]
> TLS certificate verification is enabled by default for Elasticsearch connections. Use `--no-verify-certs` only when connecting to a trusted cluster with self-signed or otherwise unverifiable certificates.


## Appendix

### evtx2json

**evtx2es** also includes `evtx2json`, a command-line tool for converting Windows Event Logs into JSON files. :sushi: :sushi: :sushi:

```bash
$ evtx2json /path/to/your/file.evtx /path/to/output/target.json
```

You can also convert `.evtx` files directly into a Python `List[dict]` object:

```python
from evtx2es import evtx2json

result: List[dict] = evtx2json('/path/to/your/file.evtx')
```


## Output Format Example

The following example uses a sample `.evtx` file from [JPCERT/CC:LogonTracer](https://github.com/JPCERTCC/LogonTracer).

```json
[
  {
    "@timestamp": "2016-10-06T01:47:07.509504Z",
    "event": {
      "action": "eventlog-security-1102",
      "category": [
        "host"
      ],
      "type": [
        "info"
      ],
      "kind": "event",
      "provider": "microsoft-windows-eventlog",
      "module": "windows",
      "dataset": "windows.eventlog",
      "code": 1102,
      "created": "2016-10-06T01:47:07.509504Z"
    },
    "winlog": {
      "channel": "Security",
      "computer_name": "WIN-WFBHIBE5GXZ.example.co.jp",
      "event_id": 1102,
      "opcode": 0,
      "record_id": 227126,
      "task": 104,
      "version": 0,
      "provider": {
        "name": "Microsoft-Windows-Eventlog",
        "guid": "{fc65ddd8-d6ef-4962-83d5-6e5cfe9ce148}"
      }
    },
    "userdata": {
      "LogFileCleared": {
        "#attributes": {
          "xmlns:auto-ns3": "http://schemas.microsoft.com/win/2004/08/events",
          "xmlns": "http://manifests.microsoft.com/win/2004/08/windows/eventlog"
        },
        "SubjectUserSid": "S-1-5-21-1524084746-3249201829-3114449661-500",
        "SubjectUserName": "Administrator",
        "SubjectDomainName": "EXAMPLE",
        "SubjectLogonId": "0x32cfb"
      }
    },
    "process": {
      "pid": 960,
      "thread": {
        "id": 3020
      }
    },
    "log": {
      "file": {
        "path": "/path/to/your/Security.evtx"
      }
    },
    "tags": [
      "eventlog"
    ]
  },
  ...
]
```


## Performance Evaluation (v1.8.0)

Performance was evaluated using a sample `.evtx` file from [JPCERT/CC:LogonTracer](https://github.com/JPCERTCC/LogonTracer) (approx. 30MB of binary data).

```bash
$ time uv run evtx2es Security.evtx 
Currently Importing Security.evtx.
1it [00:08,  8.09s/it]
Bulk import completed: 1 batches processed
Successfully indexed: 62031 documents
Import completed.

________________________________________________________
Executed in    8.60 secs    fish           external
   usr time    4.85 secs  481.00 micros    4.85 secs
   sys time    0.40 secs    0.00 micros    0.40 secs
```


### Running Environment

```
OS: Ubuntu 20.04 (Dev Container on WSL2)
CPU: Intel Core i5-12400F
RAM: DDR4 32GB
```

The tests were conducted within the provided development container, pushing data into a local [Elasticsearch 9.0.2 Docker container](https://hub.docker.com/_/elasticsearch).


## Installation

### From PyPI

```bash
$ pip install evtx2es
```

### With uv

```bash
$ uv add evtx2es
```

### From GitHub Releases

Standalone binaries built with Nuitka are available from GitHub Releases for systems without a Python environment.

```bash
$ chmod +x ./evtx2es
$ ./evtx2es {{options...}}
```

```powershell
> evtx2es.exe {{options...}}
```

## Contributing

The source code for **evtx2es** is hosted on GitHub: https://github.com/sumeshi/evtx2es.
Please report issues and feature requests. :sushi: :sushi: :sushi:


## Included in

- [Tsurugi Linux [Lab]](https://tsurugi-linux.org/) — included in releases from 2022 to 2026
- [Drift Linux Fast/Fast XS](https://www.driftlinux.org/) — included in 2026 releases

Thank you for your interest in evtx2es!


## License

Released under the [MIT](LICENSE) License.


## Third-party licenses

The standalone binaries distributed via GitHub Releases may bundle the following third-party libraries.
These libraries remain under their original licenses.

### Apache-2.0

- [elasticsearch-py / elasticsearch](https://github.com/elastic/elasticsearch-py) — licensed under the Apache License 2.0.
  - Bundled version: `elasticsearch==9.4.1`
  - License text: https://github.com/elastic/elasticsearch-py/blob/main/LICENSE

### MIT

- [evtx / pyevtx-rs](https://github.com/omerbenamram/pyevtx-rs) — licensed under the MIT License.
  - Bundled version: `evtx==0.11.1`
  - License text: https://github.com/omerbenamram/pyevtx-rs/blob/master/pyproject.toml

- [urllib3](https://github.com/urllib3/urllib3) — licensed under the MIT License.
  - Bundled version: `urllib3==2.6.3`
  - License text: https://github.com/urllib3/urllib3/blob/main/LICENSE.txt

### Apache-2.0 OR MIT, with MPL-2.0 components

- [orjson](https://github.com/ijl/orjson) — licensed under Apache-2.0 OR MIT, and contains source code licensed under MPL-2.0.
  - Bundled version: `orjson==3.11.9`
  - License text:
    - https://github.com/ijl/orjson/blob/master/LICENSE-APACHE
    - https://github.com/ijl/orjson/blob/master/LICENSE-MIT
    - https://github.com/ijl/orjson/blob/master/LICENSE-MPL-2.0

### MIT and MPL-2.0

- [tqdm](https://github.com/tqdm/tqdm) — licensed under MIT, with MPL-2.0-covered files/components.
  - Bundled version: `tqdm==4.67.3`
  - License text: https://github.com/tqdm/tqdm/blob/master/LICENCE
