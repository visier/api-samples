import logging
import os

from sqlalchemy import String, Float, Integer, BigInteger, Boolean, insert, create_engine, Column, Table, MetaData
from sqlalchemy.orm import sessionmaker

from constants import *

logger = logging.getLogger(__name__)


class DataStore:
    """Simple data store for saving result tables to a database."""

    VISIER_TO_SQL_TYPES = {
        'String': String,
        'Date': BigInteger,
        'Number': Float,
        'Integer': Integer,
        'Boolean': Boolean
    }
    SQLITE_PREFIX = 'sqlite:///'

    def __init__(self, db_url: str, echo: bool = False) -> None:
        # Create the database directory if it is SQLite
        if db_url.startswith(self.SQLITE_PREFIX):
            db_path = db_url[len(self.SQLITE_PREFIX):]
            db_dir = os.path.dirname(db_path)
            os.makedirs(db_dir, exist_ok=True)

        self.engine = create_engine(db_url, echo=echo)
        self.metadata = MetaData()
        self.metadata.reflect(self.engine)
        self.session_make = sessionmaker(bind=self.engine)

    def drop_table_if_exists(self, table_name: str) -> None:
        """Drops a table from the database if exists."""
        table: Table = self.metadata.tables.get(table_name, None)
        if table is not None:
            table.drop(self.engine, checkfirst=True)
            self.metadata.remove(table)
            logger.info(f"Dropped table {table_name}.")
        else:
            logger.info(f"Table {table_name} does not exist.")

    def create_table(self, analytic_object: str, query_columns: dict, table_columns: dict) -> None:
        """Creates a table in the database based on the query and table columns."""
        columns = []
        for query_column in query_columns:
            for table_column in table_columns:
                query_column_name = query_column[COLUMN_DEFINITION][PROPERTY][NAME][len(analytic_object) + 1:]
                if query_column_name == table_column[NAME]:
                    column = Column(query_column[COLUMN_NAME], self.VISIER_TO_SQL_TYPES[table_column[DATA_TYPE]])
                    columns.append(column)

        Table(analytic_object, self.metadata, *columns)
        self.metadata.create_all(self.engine)
        logger.info(f"Created table {analytic_object}.")

    def save_to_db(self, table_name: str, rows: list[list], chunk_size: int = 1000) -> None:
        """Saves a list of rows to the database in chunks."""
        with self.session_make() as session:
            table = self.metadata.tables[table_name]
            insert_stmt = insert(table)

            # Convert the list of rows into a list of dictionaries
            columns = table.columns.keys()
            data = [dict(zip(columns, row)) for row in rows]

            # Insert data in chunks
            for i in range(0, len(data), chunk_size):
                chunk = data[i:i + chunk_size]
                session.execute(insert_stmt, chunk)
            logger.info(f"Inserted {len(data)} rows into table {table_name}.")

            session.commit()
