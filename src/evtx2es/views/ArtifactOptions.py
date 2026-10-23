"""Windows Event Log options layered on the common CLI."""

from datetime import datetime, timezone


class ArtifactOptions:
    supports_multiprocessing = True

    def _define_artifact_options(self):
        self.parser.add_argument(
            "--datasetdate",
            default=None,
            help=(
                "Shift timestamps based on the latest record's TimeCreated value "
                "(MM/DD/YYYY.HH:MM:SS, interpreted as UTC)."
            ),
        )

    def get_shift_and_tags(self):
        # shift timestamp
        if getattr(self.args, "datasetdate", None) is not None:
            dataset_date = datetime.strptime(self.args.datasetdate, "%m/%d/%Y.%H:%M:%S")
            shift = datetime.now(timezone.utc) - dataset_date.replace(
                tzinfo=timezone.utc
            )
        else:
            shift = None

        # Parse tags
        additional_tags = None
        if getattr(self.args, "tags", ""):
            additional_tags = [
                tag.strip() for tag in self.args.tags.split(",") if tag.strip()
            ]

        return shift, additional_tags
