"""Zotero integration for Cognitia Brain."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class ZoteroIntegration:
    """Integration with Zotero reference manager."""

    def __init__(self, config_path: Path = Path("config.yaml")):
        self.config_path = config_path
        self.zotero_config = self._load_config()

    def _load_config(self) -> Dict:
        """Load Zotero configuration from config.yaml."""
        try:
            import yaml
            if self.config_path.exists():
                with self.config_path.open("r", encoding="utf-8") as f:
                    data = yaml.safe_load(f) or {}
                    return data.get("zotero", {})
        except Exception as e:
            logger.error(f"Error loading Zotero config: {e}")
        return {}

    def is_configured(self) -> bool:
        """Check if Zotero integration is configured."""
        return bool(self.zotero_config.get("api_key") and self.zotero_config.get("library_id"))

    def get_library_items(self, limit: int = 100) -> List[Dict]:
        """Get items from Zotero library."""
        if not self.is_configured():
            logger.warning("Zotero integration not configured")
            return []

        try:
            import requests

            api_key = self.zotero_config["api_key"]
            library_id = self.zotero_config["library_id"]
            library_type = self.zotero_config.get("library_type", "user")

            base_url = f"https://api.zotero.org/{library_type}s/{library_id}"
            headers = {
                "Zotero-API-Key": api_key,
                "Content-Type": "application/json"
            }

            response = requests.get(
                f"{base_url}/items",
                headers=headers,
                params={"limit": limit, "format": "json"}
            )

            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"Zotero API error: {response.status_code}")
                return []

        except Exception as e:
            logger.error(f"Error fetching Zotero items: {e}")
            return []

    def get_item_details(self, item_key: str) -> Optional[Dict]:
        """Get details of a specific Zotero item."""
        if not self.is_configured():
            return None

        try:
            import requests

            api_key = self.zotero_config["api_key"]
            library_id = self.zotero_config["library_id"]
            library_type = self.zotero_config.get("library_type", "user")

            base_url = f"https://api.zotero.org/{library_type}s/{library_id}"
            headers = {
                "Zotero-API-Key": api_key,
                "Content-Type": "application/json"
            }

            response = requests.get(
                f"{base_url}/items/{item_key}",
                headers=headers,
                params={"format": "json"}
            )

            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"Zotero API error: {response.status_code}")
                return None

        except Exception as e:
            logger.error(f"Error fetching Zotero item: {e}")
            return None

    def search_items(self, query: str, limit: int = 50) -> List[Dict]:
        """Search items in Zotero library."""
        if not self.is_configured():
            return []

        try:
            import requests

            api_key = self.zotero_config["api_key"]
            library_id = self.zotero_config["library_id"]
            library_type = self.zotero_config.get("library_type", "user")

            base_url = f"https://api.zotero.org/{library_type}s/{library_id}"
            headers = {
                "Zotero-API-Key": api_key,
                "Content-Type": "application/json"
            }

            response = requests.get(
                f"{base_url}/items",
                headers=headers,
                params={
                    "q": query,
                    "limit": limit,
                    "format": "json"
                }
            )

            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"Zotero API error: {response.status_code}")
                return []

        except Exception as e:
            logger.error(f"Error searching Zotero items: {e}")
            return []

    def extract_metadata(self, item: Dict) -> Dict:
        """Extract metadata from Zotero item."""
        data = item.get("data", {})

        return {
            "key": data.get("key"),
            "title": data.get("title"),
            "authors": [
                f"{creator.get('lastName', '')}, {creator.get('firstName', '')}"
                for creator in data.get("creators", [])
            ],
            "year": data.get("date", "")[:4] if data.get("date") else None,
            "doi": data.get("DOI"),
            "url": data.get("url"),
            "abstract": data.get("abstractNote"),
            "tags": [tag.get("tag") for tag in data.get("tags", [])],
            "item_type": data.get("itemType"),
            "publication": data.get("publicationTitle"),
            "volume": data.get("volume"),
            "issue": data.get("issue"),
            "pages": data.get("pages")
        }

    def export_to_bibtex(self, items: List[Dict]) -> str:
        """Export Zotero items to BibTeX format."""
        bibtex_entries = []

        for item in items:
            metadata = self.extract_metadata(item)
            key = metadata.get("key", "unknown")
            title = metadata.get("title", "Untitled")
            authors = " and ".join(metadata.get("authors", ["Unknown"]))
            year = metadata.get("year", "")
            doi = metadata.get("doi", "")
            url = metadata.get("url", "")

            entry = f"""@article{{{key},
  title = {{{title}}},
  author = {{{authors}}},
  year = {{{year}}},"""

            if doi:
                entry += f"\n  doi = {{{doi}}},"
            if url:
                entry += f"\n  url = {{{url}}},"

            entry += "\n}"
            bibtex_entries.append(entry)

        return "\n\n".join(bibtex_entries)

    def sync_with_cognitia(self, cognitia_db) -> Dict:
        """Sync Zotero items with Cognitia database."""
        if not self.is_configured():
            return {"status": "not_configured", "synced": 0}

        try:
            items = self.get_library_items(limit=1000)
            synced = 0

            for item in items:
                metadata = self.extract_metadata(item)

                # Check if item already exists in Cognitia
                if metadata.get("doi"):
                    existing = cognitia_db.search(metadata["doi"], n_results=1)
                    if existing and existing["documents"] and existing["documents"][0]:
                        continue

                # Add to Cognitia if not exists
                if metadata.get("title"):
                    # This would need to be implemented in the pipeline
                    # For now, just log the sync
                    logger.info(f"Would sync Zotero item: {metadata['title']}")
                    synced += 1

            return {"status": "success", "synced": synced, "total": len(items)}

        except Exception as e:
            logger.error(f"Error syncing with Zotero: {e}")
            return {"status": "error", "error": str(e)}


# Global Zotero integration instance
zotero_integration = ZoteroIntegration()
