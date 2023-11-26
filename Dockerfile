# --- build stage ---
FROM python:3.11-bullseye AS builder

# configure poetry
RUN pip install poetry
RUN poetry config virtualenvs.create false

# install dependencies
WORKDIR /app
COPY . /app
RUN poetry install --no-dev
RUN poetry build


# --- execute stage ---
FROM python:3.11-bullseye AS app
WORKDIR /app
COPY --from=builder /app/dist/ /opt
RUN pip install --find-links=/opt evtx2es

# you can rewrite this command when running the docker container.
# ex. docker run -t --rm -v $(pwd):/app evtx2es:latest evtx2json Security.evtx out.json
CMD ["evtx2es", "-h"]
