import os

from pgdb.database import Database
from pgdb.table import Table


def connect(url=None, schema=None, sql_path='sql'):
    """ Open a new connection to postgres via psycopg2/sqlalchemy
        db = pgdb.connect('')
    """
    if url is None:
        url = os.environ.get('DATABASE_URL')
    return Database(url, schema)
