"""Compose Contract Signing's immutable template catalog under its archive root."""
import os
from pathlib import Path

from infrastructure.file.contract_template_store import FileContractTemplateStore
from infrastructure.file.contract_template_workbook import OpenpyxlContractTemplateWorkbook
from subsystems.contract_signing.template_management import ContractTemplateManagement


def get_contract_template_catalog() -> FileContractTemplateStore:
    configured = os.getenv('CONTRACT_DOCUMENT_ARCHIVE_ROOT', '').strip()
    root = Path(configured) if configured else Path(__file__).resolve().parents[2] / 'runtime_data' / 'contracts'
    return FileContractTemplateStore(root / 'template-catalog')


def get_contract_template_management() -> ContractTemplateManagement:
    return ContractTemplateManagement(get_contract_template_catalog(), OpenpyxlContractTemplateWorkbook())
