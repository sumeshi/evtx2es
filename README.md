# Evtx2es
Import Windows EventLogs(.evtx files) to ElasticSearch.

Powered by [pyevtx-rs](https://github.com/omerbenamram/pyevtx-rs).  
Inspired by [EvtxtoElk](https://github.com/dgunter/evtxtoelk).

# Usage
```bash
$ evtx2es /path/to/your/file.evtx
```

or

```python
from evtx2es import evtx2es

if __name__ == '__main__':
    filepath = './foobar.evtx'
    evtx2es(filepath)
```

## Options
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

# Install
## via pip
```
$ pip install git+https://github.com/sumeshi/evtx2es
```
