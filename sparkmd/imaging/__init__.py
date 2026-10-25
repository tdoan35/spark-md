"""Device-independent ingestion; GPU detector imports are deferred until called."""
from .series import select_series, summarize_series
from .volume import Volume, dicom_to_volume
from .pipeline import run_analysis

__all__ = ['Volume', 'dicom_to_volume', 'select_series', 'summarize_series', 'run_analysis']
