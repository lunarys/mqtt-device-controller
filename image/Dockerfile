FROM python:alpine

RUN pip install pyyaml paho-mqtt

COPY ./device-controller.py /src/device-controller.py
WORKDIR /src

CMD ["python","device-controller.py"]
