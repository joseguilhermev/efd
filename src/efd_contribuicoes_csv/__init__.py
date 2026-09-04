"""Conversor de EFD Contribuicoes para CSV analitico."""

from .comparison import (
    COMPARISON_COLUMNS,
    ComparisonResult,
    EFDComparisonError,
    compare_efd_files,
)
from .converter import COLUMNS, ConversionResult, convert_file
from .indicators import INDICATOR_COLUMNS, IndicatorResult, generate_indicator_csv
from .workflow import (
    SCOPE_COLUMNS,
    AnnualEFDInventory,
    EFDInventoryError,
    WorkflowResult,
    discover_annual_efd_input,
    process_annual_efd_input,
    process_efd_files,
)

__all__ = [
    "COLUMNS",
    "COMPARISON_COLUMNS",
    "INDICATOR_COLUMNS",
    "SCOPE_COLUMNS",
    "AnnualEFDInventory",
    "ComparisonResult",
    "ConversionResult",
    "EFDComparisonError",
    "EFDInventoryError",
    "IndicatorResult",
    "WorkflowResult",
    "compare_efd_files",
    "convert_file",
    "discover_annual_efd_input",
    "generate_indicator_csv",
    "process_annual_efd_input",
    "process_efd_files",
]
