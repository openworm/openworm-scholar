from alpine:latest

RUN apk add --no-cache python3-dev \
    && pip3 install --upgrade pip

WORKDIR /ow_scholar

COPY . /ow_scholar

RUN pip3 --no-cache-dir install -r requirements.txt                                                                            

EXPOSE 3000

ENTRYPOINT  ["python3"]

CMD ["slack_bot.py"]
