FROM python:3

WORKDIR /usr/src/app

RUN apt update

COPY requirements.txt ./

RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD [ "python", "./foodbot.py" ]

