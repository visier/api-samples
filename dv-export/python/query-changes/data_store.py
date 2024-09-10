import logging
from typing import Set, List

from sqlalchemy import String, Float, Integer, BigInteger, Boolean, insert, create_engine, Column, Table, MetaData
from sqlalchemy.orm import sessionmaker
from sqlalchemy_utils import database_exists, create_database
from visier_api_analytic_model import PropertiesDTO
from visier_api_data_out import GoogleProtobufAny, PropertyColumnDTO

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

    def delete_rows(self, table_name: str, column_name: str, values: Set[str]) -> None:
        """Deletes rows from a table based on the column name and values."""
        with self.session_make() as session:
            table = self.metadata.tables[table_name]
            delete_stmt = table.delete().where(table.c[column_name].in_(values))
            result = session.execute(delete_stmt)
            session.commit()
            logger.info(f"Deleted {result.rowcount} rows from table {table_name}.")

    def create_table(self, analytic_object_name: str,
                     query_columns: List[PropertyColumnDTO],
                     properties_dto: PropertiesDTO) -> None:
        """Creates a table in the database based on the query and table columns."""
        properties_dict = {prop.id: prop for prop in properties_dto.properties}
        columns: List[Column] = []
        for query_column in query_columns:
            prop = properties_dict.get(query_column.column_definition.var_property.name)
            if prop is None:
                logger.warning(f"Property not found for column {query_column}.")
                continue
            column: Column = Column(query_column.column_name, self.VISIER_TO_SQL_TYPES[prop.primitive_data_type])
            columns.append(column)

        Table(analytic_object_name, self.metadata, *columns)
        self.metadata.create_all(self.engine)
        logger.info(f"Created table {analytic_object_name}.")

    def save_to_db(self, table_name: str, protobuf_changes: List[GoogleProtobufAny], chunk_size: int = 1000) -> None:
        """Saves a list of rows to the database in chunks."""
        with self.session_make() as session:
            table = self.metadata.tables[table_name]
            insert_stmt = insert(table)

            # Convert the list of rows into a list of dictionaries
            columns = table.columns.keys()
            data = [dict(zip(columns, [v for _, v in sorted(change.to_dict().items(), key=lambda x: int(x[0]))]))
                    for change in protobuf_changes]

            # Insert data in chunks
            for i in range(0, len(data), chunk_size):
                chunk = data[i:i + chunk_size]
                session.execute(insert_stmt, chunk)
            logger.info(f"Inserted {len(data)} rows into table {table_name}.")

            session.commit()
