#FROM public.ecr.aws/lambda/python:3.6.2020.12.18.22
FROM python:3.6

WORKDIR /app
COPY ./requirements.txt /app
RUN pip install -r requirements.txt

COPY graph.py /app
COPY assets/ /app/assets
COPY dash_app.py /app
COPY mysql_config.py /app

ENV PORT 8080
EXPOSE 8080

# Set the CMD to your handler
CMD [ "python3", "dash_app.py" ]
