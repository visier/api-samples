from dataclasses import dataclass
from enum import Enum


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


def extract_tables(tables_metadata: list[dict[str, any]]) -> list[TableInfo]:
    tables: list[TableInfo] = []

    for table_metadata in tables_metadata:
        table_name = table_metadata['name']
        common_columns_and_files = table_metadata['commonColumns']
        new_columns_and_files = table_metadata['newColumns']
        deleted_columns = table_metadata['deletedColumns']

        common_columns_column_infos = extract_column_infos(common_columns_and_files['columns'])
        common_columns_file_infos = extract_file_infos(common_columns_and_files['files'])

        new_columns_column_infos = extract_column_infos(new_columns_and_files['columns'])
        new_columns_file_infos = extract_file_infos(new_columns_and_files['files'])

        tables.append(TableInfo(
            table_name,
            ColumnsMetadata(
                ColumnInfoAndFileInfo(common_columns_column_infos, common_columns_file_infos),
                ColumnInfoAndFileInfo(new_columns_column_infos, new_columns_file_infos),
                deleted_columns
            )
        ))

    return tables


def extract_file_infos(files: list[dict]) -> list[FileInfo]:
    file_infos = []
    for file in files:
        file_id = file['fileId']
        file_name = file['filename']
        file_infos.append(FileInfo(file_id, file_name))
    return file_infos


def extract_column_infos(columns: list[dict]) -> list[ColumnInfo]:
    column_infos = []
    for common_column in columns:
        name = common_column['name']
        data_type: str = common_column['dataType']
        data_type_enum: DVExportDataType = string_to_data_type(data_type)
        allows_null = bool(common_column['allowsNull'])
        is_primary_key = bool(common_column['isPrimaryKeyComponent'])
        column_infos.append(ColumnInfo(name, data_type_enum, allows_null, is_primary_key))
    return column_infos
