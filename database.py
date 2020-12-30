import arxiv
import pymysql
import pandas as pd
import datetime
import time
import mysql_config
MAX_ARTICLES = 10000

def make_entry(d):
    """ Create database entry from query result"""
    id_ = d['id']
    updated = datetime.datetime.strptime(d['updated'], '%Y-%m-%dT%H:%M:%SZ')
    title = d['title']
    summary = d.get('summary','')
    tags = ', '.join([v['term'] for v in d['tags']])
    authors = ', '.join(d['authors'])
    return id_, updated, title, summary, tags, authors

if __name__ == '__main__':

    conn = pymysql.connect(mysql_config.host,
                           user=mysql_config.name,
                           passwd=mysql_config.password,
                           db = 'arxiv',
                           connect_timeout=5,
                           port=mysql_config.port)
    c = conn.cursor()

    c.execute('''create table if not exists articles
                (id VARCHAR(100) unique, updated DATETIME, title TINYTEXT, summary TEXT, tags TINYTEXT, authors MEDIUMTEXT)''')

    c.execute('''create table if not exists users
                (id INTEGER NOT NULL AUTO_INCREMENT,
                created DATETIME,
                name VARCHAR(100),
                PRIMARY KEY (id))''')

    if not len(pd.read_sql(''' SELECT * FROM users''', conn)): #Add test user if table empty
        c.execute('''insert into users (id, created, name)
                      values (NULL, %s, %s)''',
                      (datetime.datetime.now(),'johndoe'))

    c.execute('''create table if not exists bookmarks
                (id INTEGER NOT NULL AUTO_INCREMENT,
                 article_id VARCHAR(100),
                 user_id INTEGER,
                 created DATETIME,
                 PRIMARY KEY(id))''')


    latest = pd.read_sql('''SELECT
                Max(updated) as dt
                FROM articles''', conn)['dt'][0]

    starting_over = False
    if latest:
        latest = datetime.datetime.strptime(latest, '%Y-%m-%d %H:%M:%S')
    else:
        print('No articles contained in table. Starting over...')
        latest = datetime.datetime(1900, 1, 1)
        starting_over = True

    cnt = 0
    for start in range(0, MAX_ARTICLES, 1000):
        if starting_over: print('{:d}/{:d} articles added'.format(start, MAX_ARTICLES))
        for q in arxiv.query('cat:cs.LG',max_results=1000, start=start, sort_by='submittedDate'):
            entry = make_entry(q)
            this_time = entry[1]
            if this_time <= latest:
                break
            else:
                c.execute('''insert into articles
                             values (%s, %s, %s, %s, %s, %s)''',make_entry(q))
                cnt += 1
        else:
            continue
        break
    if not starting_over: print('Total number of articles added: {:d}'.format(cnt))
    conn.commit()
    conn.close()
