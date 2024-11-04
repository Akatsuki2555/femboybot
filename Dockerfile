FROM python:3.13-alpine
WORKDIR /app
COPY requirements.txt /app/

RUN pip install -r /app/requirements.txt

COPY features /app/features
COPY utils /app/utils
COPY database.py /app
COPY main.py /app/
COPY LATEST_3.4.md /app/
COPY LATEST_3.2.md /app/
COPY LATEST_3.1.md /app/
COPY lang/ /app/lang/
COPY docs/ /app/docs/
COPY configs/ /app/configs/

CMD ["python", "/app/main.py"]
