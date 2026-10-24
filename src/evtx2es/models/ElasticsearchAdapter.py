"""Keep Status searchable without changing source values or document IDs."""

from copy import deepcopy

from elasticsearch import BadRequestError, NotFoundError

STATUS_MAPPING = {"type": "keyword", "ignore_above": 8191}
STATUS_CONTAINERS = ("event_data", "event_data_original")


class ElasticsearchAdapter:
    def __init__(self, client):
        self.es = client
        self._status_indices = set()

    def prepare_records(self, records, index_name):
        mapping_checked = False
        for record in records:
            winlog = record.get("winlog", {})
            if not mapping_checked and any(
                "Status" in winlog.get(container, {}) for container in STATUS_CONTAINERS
            ):
                self._ensure_status_mapping(index_name)
                mapping_checked = True
            yield record

    def prepare_source(self, record):
        return record

    def _ensure_status_mapping(self, index_name):
        if index_name in self._status_indices:
            return
        properties = {
            "winlog": {
                "properties": {
                    container: {"properties": {"Status": dict(STATUS_MAPPING)}}
                    for container in STATUS_CONTAINERS
                }
            }
        }
        try:
            metadata = self.es.indices.get(
                index=index_name, features=["aliases", "mappings"]
            )
        except NotFoundError:
            try:
                self.es.indices.create(
                    index=index_name, mappings={"properties": properties}
                )
            except BadRequestError as error:
                detail = (
                    error.body.get("error", {}) if isinstance(error.body, dict) else {}
                )
                if (
                    not isinstance(detail, dict)
                    or detail.get("type") != "resource_already_exists_exception"
                ):
                    raise
            # Index templates can disable or nest a parent even when Status
            # itself was supplied explicitly. Validate the resulting mapping
            # after creation, just as for a pre-existing index or a create race.
            metadata = self.es.indices.get(
                index=index_name, features=["aliases", "mappings"]
            )

        if index_name in metadata:
            concrete_index = index_name
        else:
            aliases = {
                name: info.get("aliases", {}).get(index_name)
                for name, info in metadata.items()
                if index_name in info.get("aliases", {})
            }
            writable = [
                name
                for name, alias in aliases.items()
                if alias.get("is_write_index") is True
            ]
            if len(writable) == 1:
                concrete_index = writable[0]
            elif (
                len(aliases) == 1
                and next(iter(aliases.values())).get("is_write_index") is not False
            ):
                concrete_index = next(iter(aliases))
            else:
                raise RuntimeError(
                    f"Cannot determine one write index for {index_name!r}; "
                    "specify a concrete index or an alias with one write index."
                )

        mapping = metadata[concrete_index].get("mappings", {})
        self._validate_container(concrete_index, "document", mapping)
        winlog = mapping.get("properties", {}).get("winlog", {})
        self._validate_container(concrete_index, "winlog", winlog)
        additions = {}
        for container in STATUS_CONTAINERS:
            path = f"winlog.{container}"
            parent = winlog.get("properties", {}).get(container, {})
            self._validate_container(concrete_index, path, parent)
            status = parent.get("properties", {}).get("Status")
            if status is None:
                additions[container] = {"properties": {"Status": dict(STATUS_MAPPING)}}
            elif status.get("type") == "text":
                keyword = status.get("fields", {}).get("keyword")
                if keyword is None:
                    extended = deepcopy(status)
                    extended.setdefault("fields", {})["keyword"] = dict(STATUS_MAPPING)
                    additions[container] = {"properties": {"Status": extended}}
                elif keyword.get("type") != "keyword":
                    self._incompatible(concrete_index, f"{path}.Status.keyword")
            elif status.get("type") != "keyword":
                self._incompatible(concrete_index, f"{path}.Status")
        # Validate both fields before writing: an incompatible old mapping is
        # never partially updated, and unrelated properties remain untouched.
        if additions:
            self.es.indices.put_mapping(
                index=concrete_index,
                properties={"winlog": {"properties": additions}},
            )
        # An alias can switch its write index between batches, so only direct
        # concrete-index requests may bypass the next metadata lookup.
        if concrete_index == index_name:
            self._status_indices.add(index_name)

    def _validate_container(self, index_name, path, mapping):
        if mapping.get("enabled") is False or mapping.get("type") not in (
            None,
            "object",
        ):
            self._incompatible(index_name, path)

    def _incompatible(self, index_name, path):
        raise RuntimeError(
            f"Index {index_name!r} has an incompatible {path} mapping; "
            "Status requires keyword or text fields in enabled objects. "
            "Use a new index with string Status mappings. "
            "Existing mapping was not changed."
        )
