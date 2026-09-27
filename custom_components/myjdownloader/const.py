"""Constants for the MyJDownloader integration."""

from datetime import timedelta

DOMAIN = "myjdownloader"
TITLE = "MyJDownloader"

SCAN_INTERVAL = timedelta(seconds=60)

LATEST_VERSION_SCAN_INTERVAL = timedelta(hours=24)
LATEST_VERSION_URL = "https://svn.jdownloader.org/build.php"
LATEST_VERSION_REGEX = (
    r".*LatestRevision:[^\d+]+(\d+)[^\d+]+Date:[^\d+]+<[^>]+>([^<]+).*"
)

ATTR_LINKS = "links"
ATTR_PACKAGES = "packages"

# Fields of the package and link lists exposed as sensor attributes. Download
# passwords, URLs, comments and download folders are left out on purpose:
# attributes are visible to every user and in templates.
QUERY_PACKAGES = [
    {
        "bytesLoaded": True,
        "bytesTotal": True,
        "childCount": True,
        "enabled": True,
        "eta": True,
        "finished": True,
        "hosts": True,
        "maxResults": -1,
        "packageUUIDs": [],
        "priority": True,
        "running": True,
        "speed": True,
        "startAt": 0,
        "status": True,
    }
]
QUERY_LINKS = [
    {
        "addedDate": True,
        "bytesLoaded": True,
        "bytesTotal": True,
        "enabled": True,
        "eta": True,
        "extractionStatus": True,
        "finished": True,
        "finishedDate": True,
        "host": True,
        "jobUUIDs": [],
        "maxResults": -1,
        "packageUUIDs": [],
        "priority": True,
        "running": True,
        "skipped": True,
        "speed": True,
        "startAt": 0,
        "status": True,
    }
]

MYJDAPI_APP_KEY = "https://git.io/JO0Dh"

SERVICE_RESTART_AND_UPDATE = "restart_and_update"
SERVICE_RUN_UPDATE_CHECK = "run_update_check"
SERVICE_START_DOWNLOADS = "start_downloads"
SERVICE_STOP_DOWNLOADS = "stop_downloads"
SERVICE_ADD_LINKS = "add_links"

FIELD_LINKS = "links"
FIELD_PRIORITY = "priority"
FIELD_AUTOSTART = "autostart"
FIELD_AUTO_EXTRACT = "auto_extract"
FIELD_PACKAGE_NAME = "package_name"
FIELD_EXTRACT_PASSWORD = "extract_password"
FIELD_DOWNLOAD_PASSWORD = "download_password"
FIELD_DESTINATION_FOLDER = "destination_folder"
FIELD_OVERWRITE_PACKAGIZER_RULES = "overwrite_packagizer_rules"
