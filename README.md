# evtx2es

[![MIT License](http://img.shields.io/badge/license-MIT-blue.svg?style=flat)](LICENSE)
[![PyPI version](https://badge.fury.io/py/evtx2es.svg)](https://badge.fury.io/py/evtx2es)
[![Python Versions](https://img.shields.io/pypi/pyversions/evtx2es.svg)](https://pypi.org/project/evtx2es/)
[![DockerHub Status](https://shields.io/docker/cloud/build/sumeshi/evtx2es)](https://hub.docker.com/r/sumeshi/evtx2es)

![evtx2es logo](https://gist.githubusercontent.com/sumeshi/c2f430d352ae763273faadf9616a29e5/raw/1bf24feb55571bf7f0c7d8d4cb04bd0a511120f2/evtx2es.svg)

Fast import of Windows EventLogs(.evtx) into Elasticsearch.

Life is too short and there is not enough time to process **huge Windows EventLogs** with **pure-Python software**.  
evtx2es uses Rust library [pyevtx-rs](https://github.com/omerbenamram/pyevtx-rs), so it runs much faster than traditional software.


## Usage

When using from the commandline interface:

```bash
$ evtx2es /path/to/your/file.evtx
```

When using from the python-script:

```python
from evtx2es import evtx2es

if __name__ == '__main__':
  filepath = '/path/to/your/file.evtx'
  evtx2es(filepath)
```

### Arguments

evtx2es supports importing from multiple files.

```bash
$ evtx2es file1.evtx file2.evtx file3.evtx
```

Also, possible to import recursively from a specific directory.

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
  Flag to run multiprocessing (fast!)
  (default: False)

--size:
  Size of the chunk to be processed for each process
  (default: 500)

--host:
  ElasticSearch host address
  (default: localhost)

--port:
  ElasticSearch port number
  (default: 9200)

--index:
  Index name of Import destination
  (default: evtx2es)

--scheme:
  Scheme to use (http, or https)
  (default: http)

--pipeline
  Elasticsearch Ingest Pipeline to use
  (default: )

--datasetdate
  Date of latest record in dataset from TimeCreated record - MM/DD/YYYY.HH:MM:SS
  (default: 0)

--login:
  The login to use if Elastic Security is enable
  (default: )

--pwd:
  The password linked to the login provided
  (default: )
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

With the Amazon Elasticsearch Serivce (ES):

```
$ evtx2es /path/to/your/file.evtx --host=example.us-east-1.es.amazonaws.com --port=443 --scheme=https --index=foobar
```

With credentials for Elastic Security:

```
$ evtx2es /path/to/your/file.evtx --host=localhost --port=9200 --index=foobar --login=elastic --pwd=******
```

Note: The current version does not verify the certificate.


## Appendix

### Evtx2json

Extra feature. :sushi: :sushi: :sushi:

Convert from Windows Eventlog to json file.

```bash
$ evtx2json /path/to/your/file.evtx /path/to/output/target.json
```

Convert from Windows Eventlog to Python List[dict] object.

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

### via PyPI
```
$ pip install evtx2es
```

### via DockerHub
```
$ docker pull sumeshi/evtx2es:latest
```

## Run with Docker
https://hub.docker.com/r/sumeshi/evtx2es


## evtx2es
```bash
# "host.docker.internal" is only available in mac and windows environments.
# For linux, use the --add-host option.
$ docker run -t --rm -v $(pwd):/app/work sumeshi/evtx2es:latest evtx2es /app/work/Security.evtx --host=host.docker.internal
```

## evtx2json
```bash
$ docker run -t --rm -v $(pwd):/app/work sumeshi/evtx2es:latest evtx2es /app/work/Security.evtx /app/work/out.json
```

Do not use the "latest" image if at all possible.  
The "latest" image is not a released version, but is built from the contents of the master branch.

## Contributing

[CONTRIBUTING](https://github.com/sumeshi/evtx2es/blob/master/CONTRIBUTING.md)

The source code for evtx2es is hosted at GitHub, and you may download, fork, and review it from this repository(https://github.com/sumeshi/evtx2es).
Please report issues and feature requests. :sushi: :sushi: :sushi:

## License

evtx2es is released under the [MIT](https://github.com/sumeshi/evtx2es/blob/master/LICENSE) License.

Powered by [pyevtx-rs](https://github.com/omerbenamram/pyevtx-rs).  
Inspired by [EvtxtoElk](https://github.com/dgunter/evtxtoelk).
