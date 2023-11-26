# Elasticsearch manipulation commands

## Check if indices exist
```bash
$ curl -X GET "http://elasticsearch:9200/_cat/indices?pretty"
```

## Test evtx to Elasticsearch import
```bash
$ evtx2es FooBar.evtx --host=elasticsearch --port=9200 --index=foobar
```

## Delete an unnecessary index
```bash
$ curl -XDELETE "http://elasticsearch:9200/foobar?pretty"
```
