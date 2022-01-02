# python 3.10
FROM python:3.10-slim

# set workdir to /app
WORKDIR /app

# copy local files to workdir
COPY . /app


# use pip to install requirements
RUN pip install .

# Expose port(s) (might have to move this to compose file)
EXPOSE 7090/udp

# entry point (specify which script to run as a commandline arg to have 1 dockerfile for many servers)
ENTRYPOINT ["python", "cli.py"]