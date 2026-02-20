ARG BUILD_FROM
FROM $BUILD_FROM

RUN apk add --no-cache python3 py3-pip

WORKDIR /app
COPY app/ /app/

RUN python3 -m pip install --no-cache-dir -r /app/requirements.txt

COPY run.sh /run.sh
RUN chmod a+x /run.sh

CMD [ "/run.sh" ]
