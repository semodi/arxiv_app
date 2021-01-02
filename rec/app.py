import pandas as pd
import pandas as pd
import numpy as np
import gensim
from gensim.utils import simple_preprocess
from gensim.parsing import PorterStemmer
from gensim.parsing.preprocessing import STOPWORDS
from gensim.corpora import Dictionary
from gensim.models import CoherenceModel
from gensim.similarities.docsim import Similarity
import gensim.similarities.docsim as ds
from gensim.utils import SaveLoad
from nltk.stem import WordNetLemmatizer
import nltk
from dask import delayed
import json
import mysql_config
import pymysql
import datetime
import os
from io import BytesIO
import pickle
import boto3

logger = gensim.similarities.docsim.logger
class BufferShard(gensim.similarities.docsim.Shard):
    def __init__(self, fname, index):
            self.dirname, self.fname = os.path.split(fname)
            self.length = len(index)
            self.cls = index.__class__
            logger.info("saving index shard to %s", self.fullname())
            pickle_save(index, self.fullname())
            self.index = self.get_index()

    def get_index(self):
        if not hasattr(self, 'index'):
            logger.debug("mmaping index from %s", self.fullname())
            self.index = load_unpickle(self.fullname())
        return self.index
gensim.similarities.docsim.Shard = BufferShard


stemmer = PorterStemmer()
s3 = boto3.client('s3')
bucket_name = 'arxiv-models'

def pickle_save(obj, fname):
    pickled = pickle.dumps(obj)
    stream = BytesIO(pickled)
    s3.upload_fileobj(stream, bucket_name, fname)
    # with open(fname, 'wb') as file:
    #     file.write(pickled)

def load_unpickle(fname):
    stream = BytesIO()
    s3.download_fileobj(bucket_name, fname, stream)
    # with open(fname, 'rb') as file:
    #     obj = pickle.loads(file.read())
    obj = pickle.loads(stream.getvalue())
    return obj

def lemmatize_stemming(text):
    return stemmer.stem(WordNetLemmatizer().lemmatize(text, pos='v'))

def connect():
    return pymysql.connect(mysql_config.host,
                       user=mysql_config.name,
                       passwd=mysql_config.password,
                       connect_timeout=5,
                       database='arxiv',
                       port = mysql_config.port)
@delayed
def preprocess(text):
    result=[]
    for token in simple_preprocess(text) :
        if token not in STOPWORDS and len(token) > 2:
            result.append(lemmatize_stemming(token))
    return result


def get_tfidf(articles, tfidf_model = None, corpus_dict = None):
    articles_preprocessed = []
    for art in articles:
        articles_preprocessed.append(preprocess(art))

    # Evaluate dask delayed functions
    for i, art in enumerate(articles_preprocessed):
        articles_preprocessed[i] = art.compute()

    if corpus_dict is None:
        corpus_dict = Dictionary(articles_preprocessed)
        pickle_save(corpus_dict, 'corpus_dict.pckl')

    bow_corpus = [corpus_dict.doc2bow(doc) for doc in articles_preprocessed]
    if tfidf_model is None:
        print('Fitting tfidf model')
        tfidf_model = gensim.models.TfidfModel(bow_corpus, id2word=corpus_dict.id2token,)
        pickle_save(tfidf_model, 'tfidf_model.pckl')
    tfidf_corpus = [tfidf_model[doc] for doc in bow_corpus]
    return tfidf_corpus, corpus_dict

def create_index():
    conn = connect()
    df = pd.read_sql(""" SELECT id, title, summary FROM articles""", conn)

    articles = (df['title'] + '. ' + df['summary']).tolist()

    tfidf_corpus, corpus_dict = get_tfidf(articles)

    index = Similarity('index', tfidf_corpus, num_features=len(corpus_dict))
    pickle_save(index, 'similarity_index.pckl')
    pickle_save(df['id'].to_dict(), 'idx_to_arxiv.pckl')
    conn.close()


def get_recommendations(user_id, cutoff_days = 20, no_papers=10):
    conn = connect()
    df_bookmarks = pd.read_sql(""" SELECT
                                   articles.id as id,
                                   bookmarks.user_id as user_id,
                                   DATE(updated) as dt,
                                   authors,
                                   title,
                                   summary
                                   FROM articles
                                   INNER JOIN bookmarks
                                   ON articles.id = bookmarks.article_id
                                   WHERE bookmarks.user_id = {}
                                   AND DATE(updated) > DATE_ADD(DATE(NOW()), INTERVAL {:d} day)""".format(user_id, -cutoff_days), conn)
    if len(df_bookmarks):
        idx_to_arxiv = load_unpickle('idx_to_arxiv.pckl')
        articles = (df_bookmarks['title'] + '. ' + df_bookmarks['summary']).tolist()
        tfidf, _ = get_tfidf(articles, load_unpickle('tfidf_model.pckl'), load_unpickle('corpus_dict.pckl'))
        index = load_unpickle('similarity_index.pckl')
        sim = index[tfidf]
        sim = np.argsort(sim, axis=-1)[:,:-1][:,::-1].T.flatten()[:no_papers*no_papers]
        _, unq = np.unique(sim, return_index=True)
        sim = sim[np.sort(unq)]
        rec = [idx_to_arxiv[s] for s in sim[:no_papers]]
        rec = pd.read_sql(""" SELECT * from articles
                     WHERE id in ('{}') """.format("','".join(rec)), conn)
        rec['updated'] = rec['updated'].apply(str)
        conn.close()
        return rec
    else:
        conn.close()
        return None

def handler(event, context):
    try:
        data = json.loads(event)
    except:
        data = {}

    user_id = data.get('user_id', 0)
    cutoff_days = data.get('cutoff_days', 20)
    no_papers = data.get('no_papers', 10)
    return get_recommendations(user_id, cutoff_days, no_papers).to_dict('records')
