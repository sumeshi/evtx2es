# Evtx2es
Import Windows EventLogs(.evtx files) to ElasticSearch.

Life is too short and there is not enough time to process huge Windows EventLogs with pure-Python software.  
evtx2es uses Rust library [pyevtx-rs](https://github.com/omerbenamram/pyevtx-rs), so it runs much faster than traditional software.

```
Note: Nov 11, 2019
    Moved main development location to gitlab
```

## Usage
```bash
$ evtx2es /path/to/your/file.evtx
```

or

```python
from evtx2es.evtx2es import evtx2es

if __name__ == '__main__':
    filepath = '/path/to/your/file.evtx'
    evtx2es(filepath)
```

### Options
```
--host: 
    ElasticSearch host address
    (default: localhost)

--port: 
    ElasticSearch port number
    (default: 9200)

--index: 
    Index name
    (default: evtx2es)

--type: 
    Document-type name
    (default: evtx2es)

--size:
    bulk insert size
    (default: 500)
```

### Examples
```
$ evtx2es /path/to/your/file.evtx --host=localhost --port=9200 --index=foo --type=bar --size=500
```

```py
if __name__ == '__main__':
    evtx2es('/path/to/your/file.evtx', host=localhost, port=9200, index='foo', type='bar', size=500)
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
### via pip
```
$ pip install git+https://github.com/sumeshi/evtx2es
```

The source code for evtx2es is hosted at GitHub, and you may download, fork, and review it from this repository(https://github.com/sumeshi/evtx2es).

Please report issues and feature requests. :sushi: :sushi: :sushi:

## License
evtx2es is released under the [MIT](https://github.com/sumeshi/evtx2es/blob/master/LICENSE) License.

Powered by [pyevtx-rs](https://github.com/omerbenamram/pyevtx-rs).  
Inspired by [EvtxtoElk](https://github.com/dgunter/evtxtoelk).
