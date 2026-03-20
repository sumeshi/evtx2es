# evtx2es

[![MIT License](http://img.shields.io/badge/license-MIT-blue.svg?style=flat)](LICENSE)
[![PyPI version](https://badge.fury.io/py/evtx2es.svg)](https://badge.fury.io/py/evtx2es)
[![Python Versions](https://img.shields.io/pypi/pyversions/evtx2es.svg)](https://pypi.org/project/evtx2es/)
[![pytest](https://github.com/sumeshi/evtx2es/actions/workflows/test.yaml/badge.svg)](https://github.com/sumeshi/evtx2es/actions/workflows/test.yaml)

![evtx2es logo](https://gist.githubusercontent.com/sumeshi/c2f430d352ae763273faadf9616a29e5/raw/1bf24feb55571bf7f0c7d8d4cb04bd0a511120f2/evtx2es.svg)

A fast library for parsing and importing Windows Event Logs into Elasticsearch.

Life is too short to process **huge Windows Event Logs** using **pure Python**.  
**evtx2es** leverages the Rust-based parser [pyevtx-rs](https://github.com/omerbenamram/pyevtx-rs), making it significantly faster than traditional tools.
It also provides parsing capable of extracting as many records as possible from corrupted, partially overwritten, or carved `.evtx` files.

## Usage

**evtx2es** can be used as a standalone command-line tool or integrated directly into your Python scripts.

```bash
$ evtx2es /path/to/your/file.evtx
```

```python
from evtx2es import evtx2es

if __name__ == '__main__':
  filepath = '/path/to/your/file.evtx'
  evtx2es(filepath)
```

### Arguments

**evtx2es** supports importing multiple files simultaneously:

```bash
$ evtx2es file1.evtx file2.evtx file3.evtx
```

You can also specify a directory to recursively import all `.evtx` files within it:

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
  Chunk size for processing (default: 500)

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
  Date of the latest record in the dataset, extracted from TimeCreated field (MM/DD/YYYY.HH:MM:SS) (default: 0)

--login:
  The login to use if Elastic Security is enabled (default: )

--pwd:
  The password associated with the provided login (default: )
```

### Examples

When using from the command line:

```
$ evtx2es /path/to/your/file.evtx --host=localhost --port=9200 --index=foobar --size=500
```

When using from a Python script:

```py
if __name__ == '__main__':
    evtx2es('/path/to/your/file.evtx', host=localhost, port=9200, index='foobar', size=500)
```

With credentials for Elastic Security:

```
$ evtx2es /path/to/your/file.evtx --host=localhost --port=9200 --index=foobar --login=elastic --pwd=******
```

**Note:** TLS/SSL certificate verification is currently disabled by default.


## Appendix

### Evtx2json

As an added bonus, **evtx2es** includes a secondary tool to convert Windows Event Logs into JSON files. :sushi: :sushi: :sushi:

```bash
$ evtx2json /path/to/your/file.evtx /path/to/output/target.json
```

You can also convert `.evtx` files directly into a Python `List[dict]` object:

```python
from evtx2es import evtx2json

if __name__ == '__main__':
  filepath = '/path/to/your/file.evtx'
  result: List[dict] = evtx2json(filepath)
```

## Output Format Example

Using the sample evtx file of [JPCERT/CC:LogonTracer](https://github.com/JPCERTCC/LogonTracer) as an example.

```
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

## Performance Evaluations (v1.8.0)

Performance was evaluated using a sample `.evtx` file from [JPCERT/CC:LogonTracer](https://github.com/JPCERTCC/LogonTracer) (approx. 30MB of binary data).

```.bash
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

The tests were conducted within the provided development container, pushing data into a local Elasticsearch 9.0.2 Docker container.  
https://hub.docker.com/_/elasticsearch

## Installation

### from PyPI

```
$ pip install evtx2es
```

### with uv

```
$ uv add evtx2es
```

### from GitHub Releases

Pre-compiled standalone binaries (built with Nuitka) are available for systems without a Python environment.

```bash
$ chmod +x ./evtx2es
$ ./evtx2es {{options...}}
```

```powershell
> evtx2es.exe {{options...}}
```

## Contributing

The source code for **evtx2es** is hosted on GitHub at https://github.com/sumeshi/evtx2es. 
Contributions, forks, and reviews are highly encouraged! Please feel free to open issues and submit feature requests. :sushi: :sushi: :sushi:

## Included in

- [Tsurugi Linux [Lab] 2022 - 2024](https://tsurugi-linux.org/) - DFIR Linux distribution

Thank you for your interest in evtx2es!

## License

evtx2es is released under the [MIT](https://github.com/sumeshi/evtx2es/blob/master/LICENSE) License.

Powered by the following libraries:
- [pyevtx-rs](https://github.com/omerbenamram/pyevtx-rs)
- [Nuitka](https://github.com/Nuitka/Nuitka)

Inspired by [EvtxtoElk](https://github.com/dgunter/evtxtoelk).
