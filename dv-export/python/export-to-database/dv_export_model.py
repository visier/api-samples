from dataclasses import dataclass
from enum import Enum

from visier_platform_sdk import DataVersionExportTableDTO, DataVersionExportFileDTO, DataVersionExportColumnDTO, \
    DataVersionExportPartFileDTO


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


def convert_table_metadata_into_table_infos(tables_metadata: list[DataVersionExportTableDTO]) -> list[TableInfo]:
    """
    Converts a list of tables from export metadata into a list of ``TableInfo``. Each ``table`` in ``tables_metadata``
    has a name and some column metadata. The column metadata includes a name, data type, whether the column allows null,
    and whether the column is a part of the primary key for the table.

    Columns are broken up into new columns, as in columns which exist in the current DV but not in the base DV,
    common columns, as in columns which are in both the base and current DV, and deleted columns, which are columns
    that exist in the base DV but are missing from the current DV.

    The column metadata also describes the file names and file IDs which populate these columns.

    A ``TableInfo`` object encapsulates all of this.

    :param tables_metadata: A list of ``DataVersionExportTableDTO`` which came from a DV export metadata response
    :return: A list of ``TableInfo`` objects which encapsulate the required metadata to create or update a table from
        a DV export
    """
    tables: list[TableInfo] = []

    for table_metadata in tables_metadata:
        table_name = table_metadata.name
        common_columns_and_files = _convert_metadata_into_infos(table_metadata.common_columns)
        new_columns_and_files = _convert_metadata_into_infos(table_metadata.new_columns)
        deleted_columns = table_metadata.deleted_columns

        tables.append(TableInfo(
            table_name,
            ColumnsMetadata(
                common_columns_and_files,
                new_columns_and_files,
                deleted_columns
            )
        ))

    return tables


def _convert_metadata_into_infos(metadata: DataVersionExportFileDTO) -> ColumnInfoAndFileInfo:
    column_infos = [_convert_to_column_info(column) for column in metadata.columns]
    file_infos = [_convert_to_file_info(file) for file in metadata.files]
    return ColumnInfoAndFileInfo(column_infos, file_infos)


def _convert_to_column_info(column: DataVersionExportColumnDTO) -> ColumnInfo:
    name = column.name
    data_type = column.data_type
    data_type_enum: DVExportDataType = string_to_data_type(data_type)
    allows_null = column.allows_null
    is_primary_key = column.is_primary_key_component
    return ColumnInfo(name, data_type_enum, allows_null, is_primary_key)


def _convert_to_file_info(part_file: DataVersionExportPartFileDTO) -> FileInfo:
    file_id = part_file.file_id
    file_name = part_file.filename
    return FileInfo(file_id, file_name)
