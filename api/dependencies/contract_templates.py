"""Compose Contract Signing's immutable template catalog under its archive root."""
from pathlib import Path
from infrastructure.file.storage_layout import ORDERS_DIRECTORY, component_storage_root

from infrastructure.file.contract_template_store import FileContractTemplateStore
from infrastructure.file.contract_template_workbook import OpenpyxlContractTemplateWorkbook
from subsystems.contract_signing.template_management import ContractTemplateManagement


def get_contract_template_catalog() -> FileContractTemplateStore:
    root = component_storage_root(ORDERS_DIRECTORY, legacy_variable="CONTRACT_DOCUMENT_ARCHIVE_ROOT",
                                  development_default=Path(__file__).resolve().parents[2] / "runtime_data" / "contracts")
    return FileContractTemplateStore(root / 'template-catalog')


def get_contract_template_management() -> ContractTemplateManagement:
    return ContractTemplateManagement(get_contract_template_catalog(), OpenpyxlContractTemplateWorkbook())
