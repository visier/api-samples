import logging
from typing import Any

from sqlalchemy import String, Float, Integer, BigInteger, Boolean, insert, create_engine, Column, Table, MetaData
from sqlalchemy.orm import sessionmaker
from sqlalchemy_utils import database_exists, create_database

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

    def __init__(self, db_url: str, echo: bool = False) -> None:
        # Create the database if it does not exist
        if not database_exists(db_url):
            create_database(db_url)

        self.engine = create_engine(db_url, echo=echo)
        self.metadata = MetaData()
        self.metadata.reflect(self.engine)
        self.session_make = sessionmaker(bind=self.engine)

    def table_exists(self, table_name: str) -> bool:
        """Checks if a table exists in the database."""
        return table_name in self.metadata.tables

    def delete_rows(self, table_name: str, column_name, values):
        """Deletes rows from a table based on the column name and values."""
        with self.session_make() as session:
            table = self.metadata.tables[table_name]
            delete_stmt = table.delete().where(table.c[column_name].in_(values))
            session.execute(delete_stmt)
            session.commit()
            logger.info(f"Deleted rows from table {table_name}.")

    def create_table(self, analytic_object: str, query_columns: dict, properties: list[dict[str, Any]]) -> None:
        """Creates a table in the database based on the query and table columns."""
        properties_dict = {prop[ID]: prop for prop in properties}
        columns = []
        for query_column in query_columns:
            prop = properties_dict.get(query_column[COLUMN_DEFINITION][PROPERTY][NAME])
            if prop is None:
                logger.warning(f"Property not found for column {query_column}.")
                continue
            column = Column(query_column[COLUMN_NAME], self.VISIER_TO_SQL_TYPES[prop[PRIMITIVE_DATA_TYPE]])
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
