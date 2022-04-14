FROM python:3.9-bullseye

# configure poetry
RUN pip install poetry
RUN poetry config virtualenvs.create false

# install dependencies
WORKDIR /app
COPY . /app
RUN poetry install --no-dev

# delete caches
RUN rm -rf ~/.cache/pip

# you can rewrite this command when running the docker container.
# ex. docker run -t --rm -v $(pwd):/app evtx2es:latest evtx2json Security.evtx out.json
CMD ["evtx2es", "-h"]
