# evtx2es

[![MIT License](http://img.shields.io/badge/license-MIT-blue.svg?style=flat)](LICENSE)
[![PyPI version](https://badge.fury.io/py/evtx2es.svg)](https://badge.fury.io/py/evtx2es)
[![Python Versions](https://img.shields.io/pypi/pyversions/evtx2es.svg)](https://pypi.org/project/evtx2es/)
[![pytest](https://github.com/sumeshi/evtx2es/actions/workflows/test.yaml/badge.svg)](https://github.com/sumeshi/evtx2es/actions/workflows/test.yaml)

![evtx2es logo](https://gist.githubusercontent.com/sumeshi/c2f430d352ae763273faadf9616a29e5/raw/1bf24feb55571bf7f0c7d8d4cb04bd0a511120f2/evtx2es.svg)

A library for fast parse & import of Windows Eventlogs into Elasticsearch.

Life is too short to process **huge Windows Eventlogs** with **pure Python**.  
**evtx2es** uses the Rust library [pyevtx-rs](https://github.com/omerbenamram/pyevtx-rs), making it much faster than traditional tools.

## Usage

**evtx2es** can be executed from the command line or incorporated into a Python script.

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

evtx2es supports simultaneous import of multiple files.

```bash
$ evtx2es file1.evtx file2.evtx file3.evtx
```

It also allows recursive import from the specified directory.

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

$ evtx2es /evtxfiles/ # The path is recursively expanded to file1~6.evtx.
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

Note: The current version does not verify the certificate.


## Appendix

### Evtx2json

An additional feature: :sushi: :sushi: :sushi:

Convert Windows Event Logs to a JSON file.

```bash
$ evtx2json /path/to/your/file.evtx /path/to/output/target.json
```

Convert Windows Event Logs to a Python List[dict] object.

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

evtx2es was evaluated using the sample evtx file of [JPCERT/CC:LogonTracer](https://github.com/JPCERTCC/LogonTracer) (about 30MB binary data).

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

Performance evaluation was conducted using the provided dev container environment with Elasticsearch 9.0.2 running in Docker (Official Image).  
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

The version compiled into a binary using Nuitka is also available for use.

```bash
$ chmod +x ./evtx2es
$ ./evtx2es {{options...}}
```

```powershell
> evtx2es.exe {{options...}}
```

## Contributing

The source code for evtx2es is hosted on GitHub. You can download, fork, and review it from this repository: https://github.com/sumeshi/evtx2es.
Please report issues and feature requests. :sushi: :sushi: :sushi:

## Included in

- [Tsurugi Linux [Lab] 2022 - 2024](https://tsurugi-linux.org/) - DFIR Linux distribution

Thank you for your interest in evtx2es!

## License

evtx2es is released under the [MIT](https://github.com/sumeshi/evtx2es/blob/master/LICENSE) License.

Powered by following libraries:
- [pyevtx-rs](https://github.com/omerbenamram/pyevtx-rs)
- [Nuitka](https://github.com/Nuitka/Nuitka)

Inspired by [EvtxtoElk](https://github.com/dgunter/evtxtoelk).
