"""
FBR DAILY UPDATE LAYER
=======================

Portable automatic update pipeline.

Flow:

1. Discover official FBR source pages
2. Discover downloadable official documents
3. Download only new official documents
4. Detect local source changes
5. Run extraction
6. Validate extraction
7. Run cleaning
8. Validate cleaning
9. Run chunking
10. Rebuild vector index when source data changed
11. Run final validation/tests
12. Save state only after successful processing

Important:

- No absolute C:\\Users\\... paths.
- Project root is detected automatically.
- Generated folders are never treated as source documents.
- Existing source documents are not deleted.
- Failed individual downloads do not crash the updater.
- State is updated only after successful processing.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path

# ============================================================
# PROJECT PATHS
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parents[1]

DATA_DIR = PROJECT_ROOT / "data"
PROFILE_DIR = DATA_DIR / "profile"

SOURCE_DIR = PROFILE_DIR / "source_docs"
RAW_SOURCE_DIR = DATA_DIR / "raw" / "04-source-docs"

EXTRACTED_DIR = SOURCE_DIR / "extracted"
CLEANED_DIR = SOURCE_DIR / "cleaned"
CHUNKS_DIR = SOURCE_DIR / "chunks"

VECTORSTORE_DIR = PROFILE_DIR / "vectorstore"

STATE_DIR = PROFILE_DIR / "daily_update"

STATE_FILE = STATE_DIR / "source_hashes.json"
LOG_FILE = STATE_DIR / "daily_update.log"
RUN_REPORT_FILE = STATE_DIR / "last_run_report.json"


# ============================================================
# OFFICIAL FBR SOURCE PAGES
# ============================================================

FBR_SOURCE_PAGES = {

    "income_tax_ordinance":
        "https://www.fbr.gov.pk/Categ/Income-Tax-Ordinance/326/1000",

    "sales_tax_act":
        "https://www.fbr.gov.pk/Categ/Sales-Tax-Act-1990/301/1000",

    "federal_excise_act":
        "https://www.fbr.gov.pk/Categ/Federal-Excise-Act/346/1000",

    "finance_acts":
        "https://www.fbr.gov.pk/Categ/Finance-Acts/620",
}


# ============================================================
# ALLOWED OFFICIAL FBR DOMAINS
# ============================================================

ALLOWED_FBR_HOSTS = {
    "www.fbr.gov.pk",
    "fbr.gov.pk",
    "download1.fbr.gov.pk",
}


# ============================================================
# DOWNLOAD SETTINGS
# ============================================================

REQUEST_TIMEOUT = 60

USER_AGENT = (
    "Mozilla/5.0 "
    "(Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 "
    "(KHTML, like Gecko) "
    "Chrome/151.0 Safari/537.36 "
    "FBR-Project-Update-Agent"
)


# ============================================================
# SUPPORTED DOCUMENT TYPES
# ============================================================

SUPPORTED_EXTENSIONS = {
    ".pdf",
    ".doc",
    ".docx",
    ".xls",
    ".xlsx",
    ".csv",
    ".json",
    ".jsonl",
    ".md",
}


# ============================================================
# GENERATED DIRECTORIES
# ============================================================

EXCLUDED_DIR_NAMES = {
    "extracted",
    "cleaned",
    "chunks",
    "vectorstore",
    "daily_update",
    "__pycache__",
}


# ============================================================
# PIPELINE SCRIPTS
# ============================================================

SCRIPTS_DIR = PROJECT_ROOT / "scripts"

PIPELINE = [
    ("Extraction", "extract_source_docs.py"),
    ("Extraction validation", "validate_source_doc_extraction.py"),
    ("Cleaning", "clean_extracted_documents.py"),
    ("Cleaning validation", "validate_cleaned_documents.py"),
    ("Chunking", "chunk_cleaned_documents.py"),
    ("Vector index", "build_vector_index.py"),
]


# ============================================================
# FINAL TESTS
# ============================================================

FINAL_TESTS = [
    "test_hybrid_retriever.py",
    "test_retrieval_quality.py",
    "test_verification_layer.py",
]


# ============================================================
# HTML LINK PARSER
# ============================================================

class LinkParser(HTMLParser):
    """Collect hyperlinks from an HTML page."""

    def __init__(self):
        super().__init__()
        self.links = []

    def handle_starttag(self, tag, attrs):

        if tag.lower() != "a":
            return

        attributes = dict(attrs)

        href = attributes.get("href")

        if href:
            self.links.append(href)


# ============================================================
# LOGGING
# ============================================================

def log(message: str):

    timestamp = datetime.now(
        tz=timezone.utc
    ).strftime("%Y-%m-%d %H:%M:%S")

    line = f"[{timestamp}] {message}"

    print(line)

    STATE_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    with open(
        LOG_FILE,
        "a",
        encoding="utf-8"
    ) as file:

        file.write(line + "\n")


# ============================================================
# NORMALIZE URL
# ============================================================

def normalize_url(url: str) -> str:
    """
    Properly encode spaces and unsafe characters in a URL.

    Example:

    https://download1.fbr.gov.pk/Docs/file name.pdf

    becomes:

    https://download1.fbr.gov.pk/Docs/file%20name.pdf
    """

    url = url.strip()

    parsed = urllib.parse.urlsplit(url)

    encoded_path = urllib.parse.quote(
        urllib.parse.unquote(parsed.path),
        safe="/:@!$&'()*+,;=-._~%"
    )

    encoded_query = urllib.parse.quote(
        parsed.query,
        safe="=&?/:@!$'()*+,;=-._~%"
    )

    return urllib.parse.urlunsplit(
        (
            parsed.scheme,
            parsed.netloc,
            encoded_path,
            encoded_query,
            parsed.fragment
        )
    )


# ============================================================
# VALIDATE FBR URL
# ============================================================

def is_allowed_fbr_url(url: str) -> bool:

    try:

        parsed = urllib.parse.urlparse(url)

        if parsed.scheme.lower() != "https":
            return False

        hostname = (
            parsed.hostname or ""
        ).lower()

        return hostname in ALLOWED_FBR_HOSTS

    except ValueError:

        return False


# ============================================================
# HTTP GET
# ============================================================

def http_get(url: str) -> bytes:
    """
    Download a URL using Python standard library.

    URLs are normalized before opening.
    """

    normalized_url = normalize_url(url)

    if not is_allowed_fbr_url(normalized_url):

        raise ValueError(
            f"URL is not an allowed official FBR URL: "
            f"{normalized_url}"
        )

    request = urllib.request.Request(
        normalized_url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": (
                "text/html,"
                "application/xhtml+xml,"
                "application/pdf,"
                "*/*"
            ),
        }
    )

    with urllib.request.urlopen(
        request,
        timeout=REQUEST_TIMEOUT
    ) as response:

        return response.read()


# ============================================================
# DOWNLOAD FILE
# ============================================================

def download_file(
    url: str,
    destination: Path
) -> bool:

    normalized_url = normalize_url(url)

    try:

        log(
            f"Downloading official document: "
            f"{normalized_url}"
        )

        data = http_get(
            normalized_url
        )

        if not data:

            log(
                "WARNING: Download returned empty data."
            )

            return False

        destination.parent.mkdir(
            parents=True,
            exist_ok=True
        )

        temporary_file = destination.with_suffix(
            destination.suffix + ".tmp"
        )

        with open(
            temporary_file,
            "wb"
        ) as file:

            file.write(data)

        temporary_file.replace(
            destination
        )

        log(
            f"Downloaded: "
            f"{destination.relative_to(PROJECT_ROOT)}"
        )

        return True

    except (
        OSError,
        UnicodeError,
        ValueError,
        urllib.error.URLError,
        urllib.error.HTTPError,
        TimeoutError
    ) as error:

        log(
            f"WARNING: Download failed "
            f"but pipeline will continue: {error}"
        )

        return False


# ============================================================
# SHA-256
# ============================================================

def calculate_file_hash(
    file_path: Path
) -> str:

    sha256 = hashlib.sha256()

    with open(
        file_path,
        "rb"
    ) as file:

        while True:

            chunk = file.read(
                1024 * 1024
            )

            if not chunk:
                break

            sha256.update(chunk)

    return sha256.hexdigest()


# ============================================================
# LOAD STATE
# ============================================================

def load_state() -> dict:

    if not STATE_FILE.exists():

        return {}

    try:

        with open(
            STATE_FILE,
            "r",
            encoding="utf-8"
        ) as file:

            data = json.load(file)

        if not isinstance(data, dict):

            log(
                "WARNING: State file does not contain "
                "a JSON object."
            )

            return {}

        return data

    except (
        OSError,
        UnicodeDecodeError,
        json.JSONDecodeError
    ) as error:

        log(
            f"WARNING: Could not read state file: {error}"
        )

        return {}


# ============================================================
# SAVE STATE
# ============================================================

def save_state(
    state: dict
):

    STATE_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    temporary_file = STATE_FILE.with_suffix(
        ".tmp"
    )

    with open(
        temporary_file,
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            state,
            file,
            indent=2,
            ensure_ascii=False
        )

    temporary_file.replace(
        STATE_FILE
    )


# ============================================================
# URL SUPPORT CHECK
# ============================================================

def is_supported_url(
    url: str
) -> bool:

    try:

        parsed = urllib.parse.urlparse(
            normalize_url(url)
        )

        path = parsed.path.lower()

        return any(
            path.endswith(extension)
            for extension in SUPPORTED_EXTENSIONS
        )

    except ValueError:

        return False


# ============================================================
# FILENAME CLEANING
# ============================================================

def clean_filename(
    filename: str
) -> str:

    filename = urllib.parse.unquote(
        filename
    )

    filename = filename.strip()

    # Windows-invalid filename characters.
    filename = re.sub(
        r'[<>:"/\\|?*]+',
        "_",
        filename
    )

    # Remove control characters.
    filename = re.sub(
        r"[\x00-\x1f\x7f]+",
        "_",
        filename
    )

    # Keep filenames readable.
    filename = re.sub(
        r"\s+",
        "_",
        filename
    )

    # Avoid trailing dots/spaces.
    filename = filename.rstrip(
        " ."
    )

    if not filename:

        filename = "fbr_document.pdf"

    return filename


# ============================================================
# FILENAME FROM URL
# ============================================================

def filename_from_url(
    url: str
) -> str:

    parsed = urllib.parse.urlparse(
        normalize_url(url)
    )

    name = Path(
        urllib.parse.unquote(
            parsed.path
        )
    ).name

    return clean_filename(
        name
    )


# ============================================================
# DISCOVER LINKS FROM OFFICIAL PAGE
# ============================================================

def discover_links_from_page(
    page_url: str
) -> list[str]:

    try:

        normalized_page_url = normalize_url(
            page_url
        )

        html = http_get(
            normalized_page_url
        ).decode(
            "utf-8",
            errors="ignore"
        )

        parser = LinkParser()

        parser.feed(
            html
        )

        links = []

        for href in parser.links:

            try:

                absolute = urllib.parse.urljoin(
                    normalized_page_url,
                    href
                )

                absolute = normalize_url(
                    absolute
                )

                if not is_allowed_fbr_url(
                    absolute
                ):
                    continue

                if not is_supported_url(
                    absolute
                ):
                    continue

                links.append(
                    absolute
                )

            except (
                ValueError,
                UnicodeError
            ):

                continue

        return sorted(
            set(links)
        )

    except (
        urllib.error.URLError,
        OSError,
        UnicodeError,
        ValueError
    ) as error:

        log(
            f"WARNING: Could not inspect FBR page "
            f"{page_url}: {error}"
        )

        return []


# ============================================================
# DOCUMENT RELEVANCE
# ============================================================

def document_is_relevant(
    url: str,
    category: str
) -> bool:

    value = urllib.parse.unquote(
        url
    ).lower()

    filename = filename_from_url(
        url
    ).lower()

    # --------------------------------------------------------
    # Income Tax Ordinance
    # --------------------------------------------------------

    if category == "income_tax_ordinance":

        return (
            "income" in value
            and (
                "ordinance" in value
                or "income-tax" in value
            )
        )

    # --------------------------------------------------------
    # Sales Tax Act
    # --------------------------------------------------------

    if category == "sales_tax_act":

        return (
            "sales" in value
            and "tax" in value
            and "act" in value
        )

    # --------------------------------------------------------
    # Federal Excise Act
    # --------------------------------------------------------

    if category == "federal_excise_act":

        return (
            "excise" in value
            and "act" in value
        )

    # --------------------------------------------------------
    # Finance Acts
    # --------------------------------------------------------

    if category == "finance_acts":

        return (
            "finance" in filename
            and "act" in filename
        )

    return False


# ============================================================
# OFFICIAL DOCUMENT DISCOVERY
# ============================================================

def discover_official_documents() -> dict:

    print()
    print("-" * 60)
    print("OFFICIAL FBR SOURCE DISCOVERY")
    print("-" * 60)

    discovered = {}

    discovery_stats = {
        "pages_checked": 0,
        "links_discovered": 0,
        "relevant_documents": 0,
        "downloaded": 0,
        "already_present": 0,
        "failed": 0,
    }

    for category, page_url in FBR_SOURCE_PAGES.items():

        discovery_stats["pages_checked"] += 1

        log(
            f"Checking official FBR page: "
            f"{category}"
        )

        links = discover_links_from_page(
            page_url
        )

        discovery_stats["links_discovered"] += len(
            links
        )

        log(
            f"Downloadable documents discovered: "
            f"{len(links)}"
        )

        for url in links:

            if not document_is_relevant(
                url,
                category
            ):
                continue

            filename = filename_from_url(
                url
            )

            destination = (
                RAW_SOURCE_DIR /
                filename
            )

            # Deduplicate by destination.
            discovered[
                str(destination).lower()
            ] = (
                url,
                destination,
                category
            )

    discovery_stats["relevant_documents"] = len(
        discovered
    )

    print()
    print(
        f"Relevant official documents found: "
        f"{len(discovered)}"
    )

    successful_files = []

    for url, destination, category in discovered.values():

        if destination.exists():

            log(
                f"Official document already exists: "
                f"{destination.name}"
            )

            discovery_stats[
                "already_present"
            ] += 1

            successful_files.append(
                destination
            )

            continue

        if download_file(
            url,
            destination
        ):

            discovery_stats[
                "downloaded"
            ] += 1

            successful_files.append(
                destination
            )

        else:

            discovery_stats[
                "failed"
            ] += 1

    print()
    print("-" * 60)
    print("OFFICIAL FBR DISCOVERY SUMMARY")
    print("-" * 60)

    print(
        f"Pages checked          : "
        f"{discovery_stats['pages_checked']}"
    )

    print(
        f"Links discovered       : "
        f"{discovery_stats['links_discovered']}"
    )

    print(
        f"Relevant documents     : "
        f"{discovery_stats['relevant_documents']}"
    )

    print(
        f"Already present        : "
        f"{discovery_stats['already_present']}"
    )

    print(
        f"New downloads          : "
        f"{discovery_stats['downloaded']}"
    )

    print(
        f"Failed downloads       : "
        f"{discovery_stats['failed']}"
    )

    if discovery_stats["failed"]:

        log(
            f"WARNING: "
            f"{discovery_stats['failed']} official "
            f"document download(s) failed."
        )

        log(
            "Existing/local documents will still "
            "be processed."
        )

    return {
        "files": successful_files,
        "stats": discovery_stats,
    }


# ============================================================
# PATH EXCLUSION
# ============================================================

def is_excluded_path(
    file_path: Path
) -> bool:

    try:

        relative_parts = (
            file_path
            .relative_to(RAW_SOURCE_DIR)
            .parts
        )

    except ValueError:

        return True

    for part in relative_parts:

        if part.lower() in EXCLUDED_DIR_NAMES:

            return True

    return False


# ============================================================
# DISCOVER LOCAL SOURCE FILES
# ============================================================

def discover_source_files() -> list[Path]:

    if not RAW_SOURCE_DIR.exists():

        log(
            f"ERROR: Source directory does not exist: "
            f"{RAW_SOURCE_DIR}"
        )

        return []

    files = []

    for file_path in RAW_SOURCE_DIR.rglob("*"):

        if not file_path.is_file():
            continue

        if is_excluded_path(
            file_path
        ):
            continue

        if file_path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            continue

        files.append(
            file_path
        )

    return sorted(
        files
    )


# ============================================================
# CHANGE DETECTION
# ============================================================

def detect_changes(
    files: list[Path],
    previous_state: dict
):

    changed = []
    unchanged = []
    current_state = {}

    for file_path in files:

        relative_path = str(
            file_path.relative_to(
                PROJECT_ROOT
            )
        ).replace(
            "\\",
            "/"
        )

        try:

            file_hash = calculate_file_hash(
                file_path
            )

        except OSError as error:

            log(
                f"WARNING: Could not hash "
                f"{relative_path}: {error}"
            )

            continue

        current_state[
            relative_path
        ] = {
            "sha256": file_hash,
            "last_checked": datetime.now(
                tz=timezone.utc
            ).isoformat(),
        }

        old_entry = previous_state.get(
            relative_path
        )

        if old_entry is None:

            changed.append(
                (
                    file_path,
                    "NEW"
                )
            )

        elif old_entry.get(
            "sha256"
        ) != file_hash:

            changed.append(
                (
                    file_path,
                    "CHANGED"
                )
            )

        else:

            unchanged.append(
                file_path
            )

    return (
        changed,
        unchanged,
        current_state
    )


# ============================================================
# RUN SCRIPT
# ============================================================

def run_script(
    script_name: str,
    stage_name: str
) -> bool:

    script_path = (
        SCRIPTS_DIR /
        script_name
    )

    if not script_path.exists():

        log(
            f"ERROR: Required script not found: "
            f"{script_path}"
        )

        return False

    print()
    print("=" * 60)
    print(
        f"RUNNING: {stage_name}"
    )
    print("=" * 60)

    log(
        f"Starting {stage_name}: "
        f"{script_name}"
    )

    command = [
        sys.executable,
        str(script_path)
    ]

    try:

        result = subprocess.run(
            command,
            cwd=PROJECT_ROOT,
            check=False
        )

        if result.returncode != 0:

            log(
                f"ERROR: {stage_name} failed "
                f"with exit code "
                f"{result.returncode}."
            )

            return False

        log(
            f"{stage_name} completed successfully."
        )

        return True

    except (
        OSError,
        ValueError,
        subprocess.SubprocessError
    ) as error:

        log(
            f"ERROR while running "
            f"{stage_name}: {error}"
        )

        return False


# ============================================================
# RUN PIPELINE
# ============================================================

def run_pipeline() -> bool:

    for stage_name, script_name in PIPELINE:

        if not run_script(
            script_name,
            stage_name
        ):

            return False

    return True


# ============================================================
# RUN FINAL TESTS
# ============================================================

def run_final_tests() -> bool:

    print()
    print("=" * 60)
    print("FINAL PIPELINE VALIDATION")
    print("=" * 60)

    for script_name in FINAL_TESTS:

        if not run_script(
            script_name,
            f"Final validation: {script_name}"
        ):

            return False

    return True


# ============================================================
# RUN REPORT + NOTIFICATION (monitoring record)
# ============================================================

def write_run_report(
    status: str,
    changed=None,
    errors=None,
    discovery_stats=None,
) -> dict:
    """
    Record update status, errors, affected files and a timestamp.

    The run report never affects the update outcome: report
    writing failures are logged and swallowed.
    """

    changed = changed or []
    errors = errors or []
    discovery_stats = discovery_stats or {}

    report = {
        "status": status,
        "timestamp": datetime.now(
            tz=timezone.utc
        ).isoformat(),
        "documents_processed": [
            {
                "path": str(
                    file_path.relative_to(PROJECT_ROOT)
                ).replace("\\", "/"),
                "change_type": change_type,
            }
            for file_path, change_type in changed
        ],
        "documents_processed_count": len(changed),
        "errors": list(errors),
        "official_documents_discovered": discovery_stats.get(
            "relevant_documents", 0
        ),
        "official_download_failures": discovery_stats.get(
            "failed", 0
        ),
    }

    try:
        STATE_DIR.mkdir(
            parents=True,
            exist_ok=True,
        )

        temporary_file = RUN_REPORT_FILE.with_suffix(
            ".tmp"
        )

        with open(
            temporary_file,
            "w",
            encoding="utf-8"
        ) as file:

            json.dump(
                report,
                file,
                indent=2,
                ensure_ascii=False
            )

        temporary_file.replace(
            RUN_REPORT_FILE
        )

    except OSError as error:

        try:

            log(
                f"WARNING: Could not write run report: {error}"
            )

        except OSError:

            # Report writing must never affect the update outcome,
            # even when the state directory itself is unusable.
            pass

    return report


def record_update_notification(
    status: str,
    report: dict,
):
    """
    Record a notification entry through the reusable notification
    tool. Failure-safe: a notification problem must NEVER break
    the daily update pipeline.
    """

    try:

        project_root_str = str(PROJECT_ROOT)

        if project_root_str not in sys.path:
            sys.path.insert(0, project_root_str)

        from app.tools.output_tools import NotificationTool

        result = NotificationTool().run(
            {
                "type": "update",
                "subject": f"FBR daily update: {status}",
                "message": (
                    f"Daily update finished with status "
                    f"'{status}'. Documents processed: "
                    f"{report.get('documents_processed_count', 0)}."
                ),
                "metadata": {
                    "status": status,
                    "documents_processed": report.get(
                        "documents_processed_count", 0
                    ),
                    "error_count": len(
                        report.get("errors", [])
                    ),
                },
            }
        )

        if not result.ok:

            log(
                f"WARNING: Notification record failed: "
                f"{result.error}"
            )

    except Exception as error:

        log(
            f"WARNING: Notification record failed "
            f"(non-fatal): {error}"
        )


def finalize_run(
    status: str,
    changed=None,
    errors=None,
    discovery_stats=None,
) -> None:
    """
    Write the run report and record the update notification.
    """

    report = write_run_report(
        status,
        changed=changed,
        errors=errors,
        discovery_stats=discovery_stats,
    )

    record_update_notification(
        status,
        report,
    )


# ============================================================
# MAIN
# ============================================================

def main() -> int:

    print()
    print("=" * 60)
    print("FBR DAILY UPDATE LAYER")
    print("=" * 60)

    log(
        "Daily update started."
    )

    # --------------------------------------------------------
    # 1. Discover official FBR updates
    # --------------------------------------------------------

    discovery_result = discover_official_documents()

    discovery_stats = discovery_result[
        "stats"
    ]

    # --------------------------------------------------------
    # 2. Discover actual local source documents
    # --------------------------------------------------------

    files = discover_source_files()

    log(
        f"Actual source documents discovered: "
        f"{len(files)}"
    )

    if not files:

        log(
            "ERROR: No supported source documents found."
        )

        finalize_run(
            "failed",
            errors=["No supported source documents found."],
            discovery_stats=discovery_stats,
        )

        return 1

    # --------------------------------------------------------
    # 3. Load previous state
    # --------------------------------------------------------

    previous_state = load_state()

    # --------------------------------------------------------
    # 4. Detect local source changes
    # --------------------------------------------------------

    changed, unchanged, current_state = detect_changes(
        files,
        previous_state
    )

    print()
    print("-" * 60)
    print("CHANGE DETECTION")
    print("-" * 60)

    print(
        f"New/changed documents : {len(changed)}"
    )

    print(
        f"Unchanged documents   : {len(unchanged)}"
    )

    # --------------------------------------------------------
    # 5. First run
    # --------------------------------------------------------

    if not previous_state:

        log(
            "No previous state found."
        )

        log(
            "Existing source files will be recorded "
            "as the initial baseline."
        )

        save_state(
            current_state
        )

        log(
            "Initial source baseline saved."
        )

        finalize_run(
            "baseline_initialized",
            changed=changed,
            discovery_stats=discovery_stats,
        )

        print()
        print("=" * 60)
        print(
            "DAILY UPDATE RESULT: "
            "BASELINE INITIALIZED"
        )
        print("=" * 60)

        print(
            "Existing source documents were recorded."
        )

        print(
            "No full rebuild was triggered."
        )

        return 0

    # --------------------------------------------------------
    # 6. No changes
    # --------------------------------------------------------

    if not changed:

        log(
            "No local source changes detected."
        )

        save_state(
            current_state
        )

        finalize_run(
            "no_changes",
            discovery_stats=discovery_stats,
        )

        print()
        print("=" * 60)
        print(
            "DAILY UPDATE RESULT: NO CHANGES"
        )
        print("=" * 60)

        print(
            f"Official documents discovered: "
            f"{discovery_stats['relevant_documents']}"
        )

        print(
            "No processing pipeline was required."
        )

        return 0

    # --------------------------------------------------------
    # 7. Show changes
    # --------------------------------------------------------

    print()
    print("Changed/New documents:")

    for file_path, change_type in changed:

        relative_path = file_path.relative_to(
            PROJECT_ROOT
        )

        print(
            f"  [{change_type}] "
            f"{relative_path}"
        )

    # --------------------------------------------------------
    # 8. Run processing pipeline
    # --------------------------------------------------------

    pipeline_success = run_pipeline()

    if not pipeline_success:

        log(
            "Daily update stopped because "
            "the processing pipeline failed."
        )

        log(
            "IMPORTANT: Source hash state "
            "was NOT advanced."
        )

        finalize_run(
            "failed",
            changed=changed,
            errors=[
                "Processing pipeline failed. "
                "See daily_update.log for the failing stage."
            ],
            discovery_stats=discovery_stats,
        )

        return 1

    # --------------------------------------------------------
    # 9. Run final validation/tests
    # --------------------------------------------------------

    tests_success = run_final_tests()

    if not tests_success:

        log(
            "Daily update stopped because "
            "final validation failed."
        )

        log(
            "IMPORTANT: Source hash state "
            "was NOT advanced."
        )

        finalize_run(
            "failed",
            changed=changed,
            errors=[
                "Final validation failed. "
                "See daily_update.log for details."
            ],
            discovery_stats=discovery_stats,
        )

        return 1

    # --------------------------------------------------------
    # 10. Save state ONLY after complete success
    # --------------------------------------------------------

    final_state = dict(
        current_state
    )

    final_state["_metadata"] = {
        "last_successful_run":
            datetime.now(
                tz=timezone.utc
            ).isoformat(),

        "documents_processed":
            len(changed),

        "official_documents_discovered":
            discovery_stats[
                "relevant_documents"
            ],

        "official_download_failures":
            discovery_stats[
                "failed"
            ],
    }

    save_state(
        final_state
    )

    log(
        "Source hash state updated successfully."
    )

    finalize_run(
        "success",
        changed=changed,
        discovery_stats=discovery_stats,
    )

    # --------------------------------------------------------
    # 11. Success
    # --------------------------------------------------------

    print()
    print("=" * 60)
    print(
        "DAILY UPDATE RESULT: SUCCESS"
    )
    print("=" * 60)

    print(
        f"Documents updated: {len(changed)}"
    )

    print(
        "Official FBR discovery completed."
    )

    print(
        "Extraction completed."
    )

    print(
        "Extraction validation completed."
    )

    print(
        "Cleaning completed."
    )

    print(
        "Cleaning validation completed."
    )

    print(
        "Chunking completed."
    )

    print(
        "Vector index completed."
    )

    print(
        "Final validation completed."
    )

    if discovery_stats["failed"]:

        print(
            f"Official document downloads skipped: "
            f"{discovery_stats['failed']}"
        )

        print(
            "See daily_update.log for details."
        )

    print(
        "Daily update completed successfully."
    )

    return 0


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":

    sys.exit(
        main()
    )