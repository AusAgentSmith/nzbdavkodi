# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 nzbdav contributors

"""JSON storage for dynamic indexers and provider caps."""

import json
import os
import tempfile

import xbmc

INDEXERS_FILENAME = "indexers.json"
PROVIDER_CAPS_FILENAME = "provider_caps.json"
ADDON_PROFILE = "special://profile/addon_data/plugin.video.nzbdav/"
STORE_VERSION = 1

_READ_ERRORS = (OSError, TypeError, ValueError)


def _profile_path():
    try:
        import xbmcvfs

        return xbmcvfs.translatePath(ADDON_PROFILE)
    except (ImportError, AttributeError, RuntimeError, TypeError, ValueError):
        return ""


def default_indexers_path():
    return os.path.join(_profile_path(), INDEXERS_FILENAME)


def default_provider_caps_path():
    return os.path.join(_profile_path(), PROVIDER_CAPS_FILENAME)


def _text(value):
    return value.strip() if isinstance(value, str) else ""


def _list(value):
    return value if isinstance(value, list) else []


def _bool_setting(value, default=False):
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in ("true", "1", "yes", "on"):
            return True
        if normalized in ("false", "0", "no", "off", ""):
            return False
    return default if value is None else bool(value)


def normalize_caps(caps):
    if not isinstance(caps, dict):
        return {}

    normalized = dict(caps)
    if "search_types" in normalized:
        normalized["search_types"] = _list(normalized.get("search_types"))
    if "supported_params" in normalized:
        normalized["supported_params"] = (
            normalized["supported_params"]
            if isinstance(normalized.get("supported_params"), dict)
            else {}
        )
    if "categories" in normalized:
        normalized["categories"] = _list(normalized.get("categories"))
    return normalized


def normalize_indexer(item):
    item = item if isinstance(item, dict) else {}
    deleted = bool(item.get("deleted"))
    if deleted:
        enabled = False
    elif "enabled" in item:
        enabled = _bool_setting(item.get("enabled"))
    else:
        enabled = True
    normalized = {
        "id": _text(item.get("id")),
        "preset_id": _text(item.get("preset_id")),
        "name": _text(item.get("name")),
        "api_url": _text(item.get("api_url")),
        "api_key": _text(item.get("api_key")),
        "enabled": enabled,
        "caps": normalize_caps(item.get("caps")),
    }
    if item.get("deleted"):
        normalized["deleted"] = True
    return normalized


def _read_json(path, empty_value, warning):
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except _READ_ERRORS:
        xbmc.log(warning, xbmc.LOGWARNING)
        return empty_value


def _ensure_parent_dir(path):
    directory = os.path.dirname(path)
    if directory and not os.path.exists(directory):
        os.makedirs(directory)


def _write_json_atomic(path, payload):
    """Write JSON atomically via a temp file + rename.

    Prevents partial writes from leaving the store in a corrupt state
    (e.g. if Kodi is killed mid-write). ``os.replace`` is atomic on
    POSIX (rename(2)) so readers always see either the old or the new
    complete file, never a half-written one.
    """
    _ensure_parent_dir(path)
    dir_name = os.path.dirname(path) or "."
    fd, tmp_path = tempfile.mkstemp(dir=dir_name, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2, sort_keys=True)
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def load_indexers(path=None):
    path = path or default_indexers_path()
    data = _read_json(path, {}, "NZB-DAV: Failed to read indexers JSON")
    indexers = data.get("indexers", []) if isinstance(data, dict) else []
    if not isinstance(indexers, list):
        return []
    return [normalize_indexer(item) for item in indexers]


def save_indexers(indexers, path=None):
    path = path or default_indexers_path()
    payload = {
        "version": STORE_VERSION,
        "indexers": [normalize_indexer(item) for item in indexers],
    }
    _write_json_atomic(path, payload)


def _normalize_provider_caps(data):
    providers = data if isinstance(data, dict) else {}
    normalized = {}
    for key, value in providers.items():
        provider_id = _text(key)
        if not provider_id or not isinstance(value, dict):
            continue
        normalized[provider_id] = {
            "base_url": _text(value.get("base_url")),
            "checked_at": _text(value.get("checked_at")),
            "caps": normalize_caps(value.get("caps")),
        }
    return normalized


def load_provider_caps(path=None):
    path = path or default_provider_caps_path()
    data = _read_json(path, {}, "NZB-DAV: Failed to read provider caps JSON")
    if not isinstance(data, dict):
        return {}
    return _normalize_provider_caps(data.get("providers", {}))


def save_provider_caps(providers, path=None):
    path = path or default_provider_caps_path()
    payload = {
        "version": STORE_VERSION,
        "providers": _normalize_provider_caps(providers),
    }
    _write_json_atomic(path, payload)
