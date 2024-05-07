from dataclasses import dataclass
from enum import Enum
from constants import *


class DVExportDataType(Enum):
    String = 1
    Integer = 2
    Number = 3
    Date = 4
    Boolean = 5


def string_to_data_type(string_value: str) -> DVExportDataType:
    try:
        return DVExportDataType[string_value]
    except KeyError:
        raise ValueError(f"No such DataType: {string_value}")


@dataclass
class FileInfo:
    file_id: int
    name: str


@dataclass
class ColumnInfo:
    name: str
    data_type: DVExportDataType
    allows_null: bool
    primary_key: bool


@dataclass
class ColumnInfoAndFileInfo:
    column_infos: list[ColumnInfo]
    file_infos: list[FileInfo]


@dataclass
class ColumnsMetadata:
    common_columns: ColumnInfoAndFileInfo
    new_columns: ColumnInfoAndFileInfo
    deleted_columns: list[str]


@dataclass
class TableInfo:
    name: str
    columns: ColumnsMetadata


def convert_table_metadata_into_table_infos(tables_metadata: list[dict[str, any]]) -> list[TableInfo]:
    """
    Converts a list of tables from export metadata into a list of ``TableInfo``. Each ``table`` in ``tables_metadata``
    has a name and some column metadata. The column metadata includes a name, data type, whether the column allows null,
    and whether the column is a part of the primary key for the table.

    Columns are broken up into new columns, as in columns which exist in the current DV but not in the base DV,
    common columns, as in columns which are in both the base and current DV, and deleted columns, which are columns
    that exist in the base DV but are missing from the current DV.

    The column metadata also describes the file names and file IDs which populate these columns.

    A ``TableInfo`` object encapsulates all of this.

    :param tables_metadata: A list of tables which came from a DV export metadata response
    :return: A list of ``TableInfo`` objects which encapsulate the required metadata to create or update a table from
        a DV export
    """
    tables: list[TableInfo] = []

    for table_metadata in tables_metadata:
        table_name = table_metadata[NAME_KEY]
        common_columns_and_files = table_metadata[COMMON_COLUMNS_KEY]
        new_columns_and_files = table_metadata[NEW_COLUMNS_KEY]
        deleted_columns = table_metadata[DELETED_COLUMNS_KEY]

        common_columns_column_infos = _convert_column_metadata_into_column_infos(common_columns_and_files[COLUMNS_KEY])
        common_columns_file_infos = _convert_file_metadata_into_file_infos(common_columns_and_files[FILES_KEY])

        new_columns_column_infos = _convert_column_metadata_into_column_infos(new_columns_and_files[COLUMNS_KEY])
        new_columns_file_infos = _convert_file_metadata_into_file_infos(new_columns_and_files[FILES_KEY])

        tables.append(TableInfo(
            table_name,
            ColumnsMetadata(
                ColumnInfoAndFileInfo(common_columns_column_infos, common_columns_file_infos),
                ColumnInfoAndFileInfo(new_columns_column_infos, new_columns_file_infos),
                deleted_columns
            )
        ))

    return tables


def _convert_file_metadata_into_file_infos(files_metadata: list[dict]) -> list[FileInfo]:
    """
    Converts a list of files from export metadata into a list of ``FileInfo``. A file has metadata describing its
    name and ID. The ID is used to identify the file when downloading from the DV export API in combination with the
    export UUID.
    :param files_metadata:
    :return: A list of ``FileInfo`` objects which encapsulate the required metadata to download files for specific
        columns from a DV export
    """
    file_infos = []
    for file in files_metadata:
        file_id = file[FILE_ID_KEY]
        file_name = file[FILENAME_KEY]
        file_infos.append(FileInfo(file_id, file_name))
    return file_infos


def _convert_column_metadata_into_column_infos(columns_metadata: list[dict]) -> list[ColumnInfo]:
    """
    Converts a list of columns from export metadata into a list of ``ColumnInfo``. A column has metadata describing
    its name, data type, whether it allows null, and whether it's a part of the primary key for the table.
    :param columns_metadata: List of columns which came from a DV export metadata response
    :return: A list of ``ColumnInfo`` objects which encapsulate the required metadata to create or update a column from
        a DV export
    """
    column_infos = []
    for common_column in columns_metadata:
        name = common_column[NAME_KEY]
        data_type: str = common_column[DATA_TYPE_KEY]
        data_type_enum: DVExportDataType = string_to_data_type(data_type)
        allows_null = bool(common_column[ALLOWS_NULL_KEY])
        is_primary_key = bool(common_column[IS_PRIMARY_KEY_COMPONENT_KEY])
        column_infos.append(ColumnInfo(name, data_type_enum, allows_null, is_primary_key))
    return column_infos
