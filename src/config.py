"""Fixed captured-record reconstruction, not historical information vintages."""
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
AGENCIES=['DOT','DEP','DSNY']
MONTHS=[4,5,6,7]
YEAR=2026
CUTOFF_OFFSETS=[35,45]
HORIZONS=[7,14,28]
ENDPOINTS=['date_only','closed_status_and_date']
FIELDS=['unique_key','created_date','closed_date','agency','status']
QUALITY_CAP_NUMERATOR=5
QUALITY_CAP_DENOMINATOR=1000

def phase(agency,month):return 'development' if agency in ['DOT','DEP'] and month in [4,5] else 'evaluation'
