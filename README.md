# evtx2es

[![MIT License](http://img.shields.io/badge/license-MIT-blue.svg?style=flat)](LICENSE)
[![PyPI version](https://badge.fury.io/py/evtx2es.svg)](https://badge.fury.io/py/evtx2es)
[![Python Versions](https://img.shields.io/pypi/pyversions/evtx2es.svg)](https://pypi.org/project/evtx2es/)
[![pytest](https://github.com/sumeshi/evtx2es/actions/workflows/test.yml/badge.svg)](https://github.com/sumeshi/evtx2es/actions/workflows/test.yml)

![evtx2es logo](https://gist.githubusercontent.com/sumeshi/c2f430d352ae763273faadf9616a29e5/raw/1bf24feb55571bf7f0c7d8d4cb04bd0a511120f2/evtx2es.svg)

Fast import of Windows EventLogs(.evtx) into Elasticsearch.

Life is too short and there is not enough time to process **huge Windows EventLogs** with **pure-Python software**.  
**evtx2es** uses Rust library [pyevtx-rs](https://github.com/omerbenamram/pyevtx-rs), so it runs much faster than traditional software.

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

Additionally, it also allows for recursive import under the specified directory.

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

$ evtx2es /evtxfiles/ # The Path is recursively expanded to file1~6.evtx.
```

### Options

```
--version, -v

--help, -h

--quiet, -q
  Flag to suppress standard output
  (default: False)

--multiprocess, -m:
  Enable multiprocessing for faster execution
  (default: False)

--size:
  Chunk size for processing (default: 500)

--host:
  ElasticSearch host address (default: localhost)

--port:
  ElasticSearch port number (default: 9200)

--index:
  Destination index name for importing (default: evtx2es)

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

When using from the commandline interface:

```
$ evtx2es /path/to/your/file.evtx --host=localhost --port=9200 --index=foobar --size=500
```

When using from the python-script:

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
    "event_record_id": 227559,
    "timestamp": "2016-10-06 01:50:49.420927 UTC",
    "winlog": {
      "channel": "Security",
      "computer_name": "WIN-WFBHIBE5GXZ.example.co.jp",
      "event_id": 4624,
      "opcode": 0,
      "provider_guid": "{54849625-5478-4994-a5ba-3e3b0328c30d}",
      "provider_name": "Microsoft-Windows-Security-Auditing",
      "record_id": 227559,
      "task": 12544,
      "version": 0,
      "process": {
        "pid": 572,
        "thread_id": 1244
      },
      "event_data": {
        "AuthenticationPackageName": "Kerberos",
        "IpAddress": "192.168.16.102",
        "IpPort": "49220",
        "KeyLength": 0,
        "LmPackageName": "-",
        "LogonGuid": "F4DC1C19-0544-BC52-0900-DFC19752C3C6",
        "LogonProcessName": "Kerberos",
        "LogonType": 3,
        "ProcessId": 0,
        "ProcessName": "-",
        "SubjectDomainName": "-",
        "SubjectLogonId": "0x0",
        "SubjectUserName": "-",
        "SubjectUserSid": "S-1-0-0",
        "TargetDomainName": "EXAMPLE",
        "TargetLogonId": "0x1fa0869",
        "TargetUserName": "WIN7_64JP_02$",
        "TargetUserSid": "S-1-5-21-1524084746-3249201829-3114449661-1107",
        "TransmittedServices": "-",
        "WorkstationName": "",
        "Status": null
      }
    },
    "log": {
      "file": {
        "name": "sample/Security.evtx"
      }
    },
    "event": {
      "code": 4624,
      "created": "2016-10-06T01:50:49.420927Z"
    },
    "@timestamp": "2016-10-06T01:50:49.420927Z"
  },
  ...
]
```

## Performance Evaluations

evtx2es was evaluated using the sample evtx file of [JPCERT/CC:LogonTracer](https://github.com/JPCERTCC/LogonTracer) (about 30MB binary data).

```.bash
$ time evtx2es ./Security.evtx
> 6.25 user 0.13 system 0:14.08 elapsed 45%CPU
```

See [Qiita](https://qiita.com/sumeshi/items/cb2fbafe59c2c83e3085) for more information.

### Running Environment

```
OS: Ubuntu 18.04
CPU: Intel Core i5-6500
RAM: DDR4 32GB
```

ElasticSearch 7.4 was running on the Docker version(Official Image).  
https://hub.docker.com/_/elasticsearch

## Installation

### from PyPI

```
$ pip install evtx2es
```

### from GitHub Releases

The version compiled into a binary using Nuitka is also available for use.

```bash
$ chmod +x ./ntfsdump
$ ./ntfsdump {{options...}}
```

```powershell
> ntfsdump.exe {{options...}}
```

## Contributing

The source code for evtx2es is hosted at GitHub, and you may download, fork, and review it from this repository(https://github.com/sumeshi/evtx2es).
Please report issues and feature requests. :sushi: :sushi: :sushi:

## License

evtx2es is released under the [MIT](https://github.com/sumeshi/evtx2es/blob/master/LICENSE) License.

Powered by following libraries:
- [pyevtx-rs](https://github.com/omerbenamram/pyevtx-rs)
- [Nuitka](https://github.com/Nuitka/Nuitka)

Inspired by [EvtxtoElk](https://github.com/dgunter/evtxtoelk).
