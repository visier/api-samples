import logging
import os
from typing import List, Dict, Any

from sqlalchemy import create_engine, Column, String, Table, MetaData, inspect
from sqlalchemy.orm import sessionmaker
from visier.connector import ResultTable

logger = logging.getLogger(__name__)


class DataStore:
    """Simple data store for saving result tables to a database."""

    def __init__(self, db_url: str, echo: bool = False) -> None:
        # Create the database directory if it is SQLite
        if db_url.startswith('sqlite:///'):
            db_path = db_url[len('sqlite:///'):]
            db_dir = os.path.dirname(db_path)
            os.makedirs(db_dir, exist_ok=True)

        self.engine = create_engine(db_url, echo=echo)
        self.metadata = MetaData()
        self.metadata.reflect(self.engine)

    def save_to_db(self, result_table: ResultTable, table_name: str, batch_size: int = 1000) -> None:
        session_maker = sessionmaker(bind=self.engine)
        logger.info(f"Saving result table into {table_name}.")
        with session_maker() as session:
            # Drop the table if it exists
            inspector = inspect(self.engine)
            if inspector.has_table(table_name):
                logger.info(f"Deleting existing table {table_name}.")
                table = Table(table_name, self.metadata, autoload_with=self.engine)
                table.drop(self.engine)
                self.metadata.remove(table)  # Ensure the table is removed from self.metadata

            # Define the table
            columns = [Column(col_name, String) for col_name in result_table.header]
            table = Table(table_name, self.metadata, *columns)
            self.metadata.create_all(self.engine)

            # Insert data using bulk insert in batches
            rows: List[Dict[str, Any]] = []
            for row in result_table.rows():
                rows.append(dict(zip(result_table.header, row)))
                if len(rows) >= batch_size:
                    session.execute(table.insert(), rows)
                    rows = []

            # Insert remaining rows
            if rows:
                session.execute(table.insert(), rows)

            # Commit the session
            session.commit()
            logger.info(f"Result table was saved into {table_name}.")
