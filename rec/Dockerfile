#FROM public.ecr.aws/lambda/python:3.6.2020.12.18.22
FROM python:3.6

COPY requirements.txt ./
RUN pip install -r requirements.txt

COPY recommend.py ./
COPY recommender_app.py ./app.py
COPY mysql_config.py ./
ENV NLTK_DATA ./

# Set the CMD to your handler
# CMD [ "app.handler" ]
CMD ["python3", "app.py"]
