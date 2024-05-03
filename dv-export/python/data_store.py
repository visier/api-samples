import logging
from abc import ABC, abstractmethod
import pandas as pd

from sqlalchemy import (Column, Table, create_engine, MetaData, Integer,
                        String, Numeric, BigInteger, Boolean, insert, text)
from dv_export_model import DVExportDataType, ColumnInfo, TableInfo

logger = logging.getLogger("data_store")


def convert_data_types_to_df_dtype_dict(column_infos) -> dict:
    column_name_to_dtype = {}
    for column in column_infos:
        dtype = ''
        if column.data_type == DVExportDataType.Date or column.data_type == DVExportDataType.Integer:
            dtype = 'Int64'
        elif column.data_type == DVExportDataType.String:
            dtype = 'object'
        elif column.data_type == DVExportDataType.Number:
            dtype = 'float64'
        elif column.data_type == DVExportDataType.Boolean:
            dtype = 'boolean'
        column_name_to_dtype[column.name] = dtype
    return column_name_to_dtype


class DataStore(ABC):

    @abstractmethod
    def create_initial_table_definition(self, tbl: TableInfo):
        pass

    @abstractmethod
    def drop_table(self, tbl_name: str):
        pass

    @abstractmethod
    def get_data_store_data_type_from_dv_export_data_type(self, data_type: DVExportDataType):
        pass

    @abstractmethod
    def insert_from_files_into_table(self,
                                     tbl_name: str,
                                     column_infos: list[ColumnInfo],
                                     file_paths_for_tbl: list[str]):
        pass

    @abstractmethod
    def drop_column(self, tbl_name: str, column_name: str):
        pass


class SQLAlchemyDataStore(DataStore):
    def __init__(self, url, echo=False):
        self.engine = create_engine(url, echo=echo)
        self.metadata = MetaData()
        self.metadata.reflect(self.engine)

    def get_data_store_data_type_from_dv_export_data_type(self, data_type: DVExportDataType):
        if data_type == DVExportDataType.String:
            return String()
        elif data_type == DVExportDataType.Integer:
            return Integer()
        elif data_type == DVExportDataType.Number:
            return Numeric()
        elif data_type == DVExportDataType.Date:
            return BigInteger()
        elif data_type == DVExportDataType.Boolean:
            return Boolean()
        else:
            raise NotImplementedError(f"data_type={data_type} has no corresponding data type for SQLAlchemy")

    def get_list_of_sql_columns(self, column_infos: list[ColumnInfo]) -> list[Column]:
        columns = []
        for column_info in column_infos:
            name = column_info.name
            sql_data_type = self.get_data_store_data_type_from_dv_export_data_type(column_info.data_type)

            # todo: Hack until https://visiercorp.atlassian.net/browse/VAN-120816 is fixed
            if column_info.name == 'Location_LEVEL':
                nullable = True
            else:
                nullable = column_info.allows_null

            columns.append(
                Column(
                    name,
                    sql_data_type,
                    primary_key=column_info.primary_key,
                    nullable=nullable
                )
            )
        return columns

    def create_initial_table_definition(self, tbl: TableInfo):
        column_names = list(map(lambda column_info: column_info.name, tbl.columns.new_columns.column_infos))
        logger.info(f"Creating table={tbl.name} with columns={column_names}")
        db_columns = self.get_list_of_sql_columns(tbl.columns.new_columns.column_infos)
        Table(tbl.name, self.metadata, *db_columns)
        self.metadata.create_all(self.engine)
        logger.info(f"Created table={tbl.name}")

    def insert_from_files_into_table(self,
                                     tbl_name: str,
                                     column_infos: list[ColumnInfo],
                                     file_paths_for_tbl: list[str]):
        logger.info(f"Begin processing data from files={file_paths_for_tbl} for table={tbl_name}")
        clm_name_to_dtype = convert_data_types_to_df_dtype_dict(column_infos)
        for file_path in file_paths_for_tbl:
            with open(file_path) as f:
                df = pd.read_csv(f, dtype=clm_name_to_dtype, on_bad_lines='warn')

                # after loading the DF, replace NaN with empty string for string columns
                str_columns = {clm_name for clm_name, dtype in clm_name_to_dtype.items() if dtype == 'object'}
                for str_column in str_columns:
                    df[str_column] = df[str_column].fillna('')

                inserts = df[df['_DiffAction_'] == '+']
                if len(inserts.index) != 0:
                    with self.engine.connect() as conn:
                        alchemy_table = self.metadata.tables[tbl_name]
                        conn.execute(
                            insert(alchemy_table),
                            inserts.to_dict('records')
                        )
                        conn.commit()
                    logger.info(f"Inserted {len(inserts.index)} records into table={tbl_name}")

    def drop_table(self, tbl_name: str):
        if tbl_name in self.metadata.tables.keys():
            alchemy_table: Table = self.metadata.tables[tbl_name]
            alchemy_table.drop(self.engine, checkfirst=True)

    def drop_column(self, tbl_name: str, column_name: str):
        with self.engine.connect() as conn:
            stmt = text(f"""ALTER TABLE {tbl_name} DROP COLUMN {column_name}""")
            conn.execute(stmt)
            conn.commit()
