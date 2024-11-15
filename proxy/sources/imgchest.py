import json

from typing import List, Optional, Dict

from bs4 import BeautifulSoup
from django.shortcuts import redirect
from django.urls import re_path

from proxy.source import ProxySource, SeriesPage, ChapterAPI, SeriesAPI, api_cache, get_wrapper


class ImageChest(ProxySource):
    def get_reader_prefix(self) -> str:
        return "imgchest"

    def shortcut_instantiator(self) -> List[re_path]:
        def handler(_, album_hash):
            slug = f"reader-{self.get_reader_prefix()}-chapter-page"
            return redirect(slug, album_hash, "1", "1")

        return [re_path(r"^p/(?P<album_hash>\w+)/$", handler)]

    @api_cache(prefix="imgchest_api_dt", time=300)
    def imgchest_common(self, meta_id: str) -> Optional[Dict]:
        url = f"https://imgchest.com/p/{meta_id}"

        resp = get_wrapper(url)
        if resp.status_code != 200:
            return None

        soup = BeautifulSoup(resp.text, "html.parser")
        page_metadata = soup.find("div", attrs={"id": "app"})
        page_data = json.loads(page_metadata.attrs["data-page"])
        post_data = page_data.get("props", {}).get("post", {})

        files = post_data.get("files", [])

        pages = [page["link"] for page in files]
        title = post_data.get("title", "No title")

        return {
            "slug": meta_id,
            "title": title,
            "description": "No description.",
            "author": "Unknown",
            "artist": "Unknown",
            "cover": pages[0],
            "groups": {"1": "imgchest"},
            "chapter_dict": {
                "1": {
                    "volume": "1",
                    "title": title,
                    "groups": {"1": pages},
                }
            },
            "chapter_list": [
                [
                    "1",
                    "1",
                    title,
                    "1",
                    "Imgchest",
                    "No date.",
                    "1",
                ],
            ],
            "pages_list": pages,
            "original_url": url,
        }

    @api_cache(prefix="imgchest_series_dt", time=300)
    def series_api_handler(self, meta_id: str) -> SeriesAPI:
        data = self.imgchest_common(meta_id)
        return data and SeriesAPI(
            slug=data["slug"],
            title=data["title"],
            description=data["description"],
            author=data["author"],
            artist=data["artist"],
            groups=data["groups"],
            cover=data["cover"],
            chapters=data["chapter_dict"]
        )

    @api_cache(prefix="imgchest_pages_dt", time=300)
    def chapter_api_handler(self, meta_id: str) -> ChapterAPI:
        data = self.imgchest_common(meta_id)
        return data and ChapterAPI(
            pages=data["pages_list"],
            series=data["slug"],
            chapter=data["slug"]
        )

    @api_cache(prefix="imgchest_series_page_dt", time=300)
    def series_page_handler(self, meta_id: str) -> SeriesPage:
        data = self.imgchest_common(meta_id)
        return data and SeriesPage(
            series=data["title"],
            alt_titles=[],
            alt_titles_str=None,
            slug=data["slug"],
            cover_vol_url=data["cover"],
            metadata=[],
            synopsis=data["description"],
            author=data["author"],
            chapter_list=data["chapter_list"],
            original_url=data["original_url"]
        )
