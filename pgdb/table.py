from hashlib import sha1

from sqlalchemy.schema import Table as SQLATable
from sqlalchemy.schema import MetaData
from sqlalchemy.schema import Column, Index

from alembic.migration import MigrationContext
from alembic.operations import Operations

from geoalchemy2 import Geometry

from pgdb.util import DatasetException
from pgdb.util import normalize_column_name


class Table(object):

    def __init__(self, db, schema, table, columns=None):
        self.db = db
        self.schema = schema
        self.name = table
        self.metadata = MetaData(schema=schema)
        self.metadata.bind = self.db.engine
        # http://docs.sqlalchemy.org/en/rel_1_0/core/metadata.html
        # if provided columns (SQLAlchemy columns), create the table
        if columns:
            self.table = SQLATable(table, self.metadata, schema=self.schema,
                                   *columns)
            self.table.create()
        # otherwise just load from db
        else:
            self.table = SQLATable(table, self.metadata, schema=self.schema,
                                   autoload=True)
        self.indexes = dict((i.name, i) for i in self.table.indexes)
        self._is_dropped = False

    @property
    def _normalized_columns(self):
        return map(normalize_column_name, self.columns)

    @property
    def columns(self):
        """
        Return list of all columns in table
        """
        return list(self.table.columns.keys())

    @property
    def sqla_columns(self):
        """
        Return all columns in table as sqlalchemy column types
        """
        return self.table.columns

    @property
    def primary_key(self):
        """
        return a list of columns making up the primary key constraint
        """
        return [c.name for c in self.table.primary_key]

    @property
    def op(self):
        ctx = MigrationContext.configure(self.engine)
        return Operations(ctx)

    def _valid_table_name(self, table_name):
        """ Check if the table name is obviously invalid. """
        if table_name is None or not len(table_name.strip()):
            raise ValueError("Invalid table name: %r" % table_name)
        return table_name.strip()

    def _update_table(self, table_name):
        self.metadata = MetaData(schema=self.schema)
        self.metadata.bind = self.db.engine
        return SQLATable(table_name, self.metadata, schema=self.schema)

    def add_primary_key(self, column="id"):
        """
        add primary key constraint to specified column
        """
        if not self.primary_key:
            sql = """ALTER TABLE {s}.{t}
                     ADD PRIMARY KEY ({c})
                  """.format(s=self.schema,
                             t=self.name,
                             c=column)
            self.db.execute(sql)

    def drop(self):
        """
        Drop the table from the database
        """
        self._is_dropped = True
        self.table.drop(self.db.engine)

    def _check_dropped(self):
        if self._is_dropped:
            raise DatasetException('the table has been dropped. this object should not be used again.')

    def create_index_geom(self, column="geom"):
        """
        create index on geometry
        """
        self.db.execute('CREATE INDEX "idx_%s_%s" ON "%s"."%s" '
                        'USING GIST ("%s")' % (self.name, column, self.schema,
                                               self.name, column))

    def create_column(self, name, type):
        """
        Explicitely create a new column ``name`` of a specified type.
        ``type`` must be a `SQLAlchemy column type <http://docs.sqlalchemy.org/en/rel_0_8/core/types.html>`_.
        ::

            table.create_column('created_at', sqlalchemy.DateTime)
        """
        self._check_dropped()
        if normalize_column_name(name) not in self._normalized_columns:
            self.op.add_column(
                self.table.name,
                Column(name, type),
                self.table.schema
            )
            self.table = self._update_table(self.table.name)

    def drop_column(self, name):
        """
        Drop the column ``name``
        ::

            table.drop_column('created_at')
        """
        self._check_dropped()
        if name in self.table.columns.keys():
            self.op.drop_column(
                self.table.name,
                name
            )
            self.table = self._update_table(self.table.name)

    def create_index(self, columns, name=None):
        """
        Create an index to speed up queries on a table. If no ``name`` is given a random name is created.
        ::

            table.create_index(['name', 'country'])
        """
        self._check_dropped()
        if not name and len(columns > 1):
            sig = '||'.join(columns)

            # This is a work-around for a bug in <=0.6.1 which would create
            # indexes based on hash() rather than a proper hash.
            key = abs(hash(sig))
            name = 'ix_%s_%s' % (self.table.name, key)
            if name in self.indexes:
                return self.indexes[name]
            key = sha1(sig.encode('utf-8')).hexdigest()[:16]
            name = 'ix_%s_%s' % (self.table.name, key)
        elif not name and len(columns == 1):
            name = columns[0]+"_idx"
        if name in self.indexes:
            return self.indexes[name]
        try:
            #self.database._acquire()
            columns = [self.table.c[c] for c in columns]
            idx = Index(name, *columns)
            idx.create(self.database.engine)
        except:
            idx = None
        #finally:
        #    self.database._release()
        self.indexes[name] = idx
        return idx
