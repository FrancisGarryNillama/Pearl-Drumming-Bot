"""
services/sheets_service.py
===========================
Handles all Google Sheets read/write operations.

Uses a Google Service Account (JSON key file) for authentication.
Finds the next empty row and inserts the required columns.

Column mapping (matches the Pearl27 tracking sheet):
  No. | Site | UserName | Drummer Name | Date | No of post | Platform | Link
"""

import os
from datetime import datetime
from pathlib import Path
from typing import Optional

import gspread
from google.oauth2.service_account import Credentials

from config import SheetsConfig, PlatformConfig
from utils.helpers import today_formatted
from utils.logger import get_logger

log = get_logger(__name__)

# Google API scopes required
_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


class SheetsService:
    """
    Google Sheets logging service.

    Authenticates with a service account, opens the target sheet,
    and appends task completion records.
    """

    # Column name → zero-based index mapping.
    # Adjust indices to match your actual sheet layout.
    COLUMN_MAP = {
        "No.":          0,
        "Site":         1,
        "UserName":     2,
        "Drummer Name": 3,
        "Date":         4,
        "No of post":   5,
        "Platform":     6,
        "Link":         7,
    }

    def __init__(self, sheets_cfg: SheetsConfig, platform_cfg: PlatformConfig):
        self.sheets_cfg  = sheets_cfg
        self.platform_cfg = platform_cfg
        self._client: Optional[gspread.Client] = None
        self._worksheet: Optional[gspread.Worksheet] = None

    # ─────────────────────────────────────────────────────────
    # Connection
    # ─────────────────────────────────────────────────────────

    def connect(self) -> bool:
        """Authenticate and open the target worksheet."""
        try:
            cred_path = Path(self.sheets_cfg.service_account_json)
            if not cred_path.exists():
                log.error(
                    f"Service account JSON not found: {cred_path}. "
                    f"See SETUP.md for instructions."
                )
                return False

            creds = Credentials.from_service_account_file(
                str(cred_path), scopes=_SCOPES
            )
            self._client = gspread.authorize(creds)
            sheet = self._client.open_by_key(self.sheets_cfg.sheet_id)
            self._worksheet = sheet.worksheet(self.sheets_cfg.sheet_name)

            log.info(
                f"✅ Connected to Google Sheets: "
                f"'{sheet.title}' / '{self.sheets_cfg.sheet_name}'"
            )
            return True

        except Exception as exc:
            log.error(f"Google Sheets connection failed: {exc}")
            return False

    # ─────────────────────────────────────────────────────────
    # Read Helpers
    # ─────────────────────────────────────────────────────────

    def _get_all_values(self) -> list[list[str]]:
        """Return all rows from the worksheet."""
        if not self._worksheet:
            raise RuntimeError("Worksheet not connected. Call connect() first.")
        return self._worksheet.get_all_values()

    def _find_next_empty_row(self) -> int:
        """
        Return the 1-based row index of the next empty row.
        Considers a row empty if the first 3 columns are all blank.
        """
        rows = self._get_all_values()
        for i, row in enumerate(rows, start=1):
            if not any(str(cell).strip() for cell in row[:3]):
                return i
        return len(rows) + 1  # Append after last row

    def _get_last_row_number(self) -> int:
        """Return the 'No.' value from the last data row (for incrementing)."""
        rows = self._get_all_values()
        # Skip header (row 0)
        for row in reversed(rows[1:]):
            val = str(row[self.COLUMN_MAP["No."]]).strip()
            if val.isdigit():
                return int(val)
        return 0

    # ─────────────────────────────────────────────────────────
    # Write
    # ─────────────────────────────────────────────────────────

    def log_task_completion(
        self,
        post_url: str,
        platform: str,
        num_posts: int = 1,
    ) -> bool:
        """
        Insert a new row into the tracking sheet.

        Args:
            post_url:  URL of the completed post
            platform:  Platform name (e.g. 'Quora', 'Reddit')
            num_posts: Number of posts processed (usually 1)

        Returns:
            True if the row was inserted successfully.
        """
        if not self._worksheet:
            log.error("Not connected to Google Sheets.")
            return False

        try:
            next_row   = self._find_next_empty_row()
            next_num   = self._get_last_row_number() + 1
            today_str  = today_formatted()  # matches MM/DD/YYYY format

            # Build the row data aligned to COLUMN_MAP
            row_data = self._build_row(
                number=next_num,
                site=self.platform_cfg.site,
                username=self.platform_cfg.account_number,
                drummer_name=self.platform_cfg.drummer_name,
                date=today_str,
                num_posts=num_posts,
                platform=platform,
                link=post_url,
            )

            log.info(
                f"Writing to sheet row {next_row}: "
                f"No.={next_num}, date={today_str}, platform={platform}"
            )

            # Update cells one-by-one to leave other columns untouched
            for col_name, col_idx in self.COLUMN_MAP.items():
                cell_value = row_data.get(col_name, "")
                if cell_value:
                    # gspread uses 1-based row and col indexing
                    self._worksheet.update_cell(next_row, col_idx + 1, str(cell_value))

            log.info(f"✅ Google Sheets row {next_row} updated successfully.")
            return True

        except Exception as exc:
            log.error(f"Failed to write to Google Sheets: {exc}")
            return False

    def _build_row(
        self,
        number: int,
        site: str,
        username: str,
        drummer_name: str,
        date: str,
        num_posts: int,
        platform: str,
        link: str,
    ) -> dict:
        """Return a column-name → value mapping for the new row."""
        return {
            "No.":          number,
            "Site":         site,
            "UserName":     username,
            "Drummer Name": drummer_name,
            "Date":         date,
            "No of post":   num_posts,
            "Platform":     platform,
            "Link":         link,
        }

    # ─────────────────────────────────────────────────────────
    # Inspect / Validate Sheet Structure
    # ─────────────────────────────────────────────────────────

    def inspect_headers(self) -> list[str]:
        """
        Return the header row of the sheet.
        Useful for verifying COLUMN_MAP alignment.
        """
        if not self._worksheet:
            return []
        try:
            return self._worksheet.row_values(1)
        except Exception as exc:
            log.warning(f"Could not read headers: {exc}")
            return []

    def verify_column_map(self) -> bool:
        """
        Compare COLUMN_MAP against actual sheet headers.
        Logs a warning for any mismatches.
        """
        headers = self.inspect_headers()
        if not headers:
            log.warning("Could not verify column map — no headers found.")
            return False

        ok = True
        for col_name, col_idx in self.COLUMN_MAP.items():
            if col_idx < len(headers):
                actual = headers[col_idx].strip()
                if actual.lower() != col_name.lower():
                    log.warning(
                        f"Column mismatch at index {col_idx}: "
                        f"expected '{col_name}', found '{actual}'"
                    )
                    ok = False
            else:
                log.warning(f"Column '{col_name}' at index {col_idx} is out of range.")
                ok = False

        if ok:
            log.info("✅ Sheet column map verified successfully.")
        return ok