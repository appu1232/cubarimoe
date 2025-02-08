import re
import json
from datetime import datetime

from bs4 import BeautifulSoup
from django.shortcuts import redirect
from django.urls import re_path

from ..source import ProxySource
from ..source.data import ChapterAPI, ProxyException, SeriesAPI, SeriesPage
from ..source.helpers import api_cache, get_wrapper


class Reddit(ProxySource):
    def get_reader_prefix(self):
        return "reddit"

    def shortcut_instantiator(self):
        def handler(request, meta_id):
            return redirect(
                f"reader-{self.get_reader_prefix()}-chapter-page",
                meta_id,
                "1",
                "1",
            )

        return [
            re_path(r"^(?:reddit|r/[a-zA-Z0-9_]+/comments)/(?P<meta_id>[\d\w]+)", handler),
            re_path(r"^(?:gallery)/(?P<meta_id>[\d\w]+)", handler),
        ]

    @staticmethod
    def image_url_handler(url):
        # transform thumbnail link from https://preview.redd.it/media_id.ext?junk
        #                           to https://i.redd.it/media_id.ext
        return re.sub(r"\?.*", "", url.replace("preview.redd.it", "i.redd.it"))

    def reddit_gallery(self, meta_id):
        resp = get_wrapper(
            f"https://www.reddit.com/gallery/{meta_id}/",
            allow_redirects=True,
            use_proxy=True,
        )

        if resp.status_code != 200:
            raise ProxyException("Failed to retrieve data from reddit.")

        soup = BeautifulSoup(resp.text, "html.parser")
        react_data = soup.find("script", {"id": "data"})

        json_data_str = "{" + react_data.text.split("{", 1)[-1]
        json_data = json.loads(json_data_str)
        all_post_data = json_data.get("posts", {}).get("models", {})
        post_metadata = [*all_post_data.values()][0]

        if post_metadata.get("media", {}).get("type") != "gallery":
            raise ProxyException("Cubari only supports reddit galleries.")

        title = post_metadata.get("title", "Couldn't find title")
        description = f"No description."  # No real description, unfortunately
        author = post_metadata.get("author", "Unknown")
        original_url = f"https://reddit.com/gallery/{meta_id}"
        date = datetime.fromtimestamp(post_metadata.get("created", 0) / 1000)

        post_media = post_metadata.get("media", {})

        gallery_images = [
            item["mediaId"] for item in post_media.get("gallery", {}).get("items", [])
        ]

        preview_images = [
            post_media.get("mediaMetadata", {}).get(i, {}).get("s", {}).get("u", "")
            for i in gallery_images
        ]

        # The preview URL is signed, so let's unsign it by doing software crimes
        def image_unsigner(img: str):
            raw_url = img.split("?")[0]
            media_id = raw_url.split("-")[-1]

            if media_id.startswith("http"):
                return media_id.replace("preview.redd.it", "i.redd.it")
            else:
                return f"https://i.redd.it/{media_id}"

        images = [image_unsigner(img) for img in preview_images]

        if not images:
            raise ProxyException("Couldn't parse out any images from the gallery.")

        return {
            "slug": meta_id,
            "title": title,
            "description": description,
            "author": author,
            "artist": "Unknown",
            "cover": images[0],
            "groups": {"1": "Reddit"},
            "chapter_dict": {
                "1": {
                    "volume": "1",
                    "title": title,
                    "groups": {"1": images},
                }
            },
            "chapter_list": [
                [
                    "1",
                    "1",
                    title,
                    "1",
                    "No group",
                    [
                        date.year,
                        date.month - 1,
                        date.day,
                        date.hour,
                        date.minute,
                        date.second,
                    ],
                    "1",
                ],
            ],
            "pages_list": images,
            "original_url": original_url,
        }

    def reddit_api(self, meta_id):
        resp = get_wrapper(
            f"https://old.reddit.com/{meta_id}.json",
            headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:122.0) Gecko/20100101 Firefox/122.0",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.5",
            },
            allow_redirects=True,
        )

        if resp.status_code != 200:
            raise ProxyException("The reddit API didn't return properly.")

        api_data = resp.json()
        try:
            if isinstance(api_data, list):
                api_data = api_data[0]["data"]["children"][0]["data"]
            else:
                api_data = api_data["data"]["children"][0]["data"]
        except (ValueError, TypeError):
            raise ProxyException(f"Failed to deserialize reddit response.")

        if (
            "is_gallery" not in api_data
            or not api_data["is_gallery"]
            or api_data["removed_by_category"] != None
        ):
            raise ProxyException("This reddit link doesn't resolve to a gallery.")

        try:
            date = datetime.utcfromtimestamp(api_data["created"])
        except ValueError:
            date = datetime.now()

        images = []
        for image in api_data["gallery_data"]["items"]:
            metadata = api_data["media_metadata"][image["media_id"]]
            if metadata["status"] != "valid" or metadata["e"] != "Image":
                continue
            url = self.image_url_handler(metadata["s"]["u"])
            images.append(url)
        if not images:
            raise ProxyException("Couldn't find any images.")

        return {
            "slug": meta_id,
            "title": api_data["title"],
            "description": "No description",
            "author": "Unknown",
            "artist": "Unknown",
            "cover": images[0],
            "groups": {"1": "Reddit"},
            "chapter_dict": {
                "1": {
                    "volume": "1",
                    "title": api_data["title"],
                    "groups": {"1": images},
                }
            },
            "chapter_list": [
                [
                    "1",
                    "1",
                    api_data["title"],
                    "1",
                    "No group",
                    [
                        date.year,
                        date.month - 1,
                        date.day,
                        date.hour,
                        date.minute,
                        date.second,
                    ],
                    "1",
                ],
            ],
            "pages_list": images,
            "original_url": f"https://www.reddit.com{api_data['permalink']}",
        }

    @api_cache(prefix="reddit_series_dt", time=300)
    def series_api_handler(self, meta_id):
        data = self.reddit_gallery(meta_id)
        return (
            SeriesAPI(
                slug=data["slug"],
                title=data["title"],
                description=data["description"],
                author=data["author"],
                artist=data["artist"],
                groups=data["groups"],
                cover=data["cover"],
                chapters=data["chapter_dict"],
            )
            if data
            else None
        )

    @api_cache(prefix="reddit_pages_dt", time=300)
    def chapter_api_handler(self, meta_id):
        data = self.reddit_gallery(meta_id)
        return (
            ChapterAPI(
                pages=data["pages_list"], series=data["slug"], chapter=data["slug"]
            )
            if data
            else None
        )

    @api_cache(prefix="reddit_series_page_dt", time=300)
    def series_page_handler(self, meta_id):
        data = self.reddit_gallery(meta_id)
        return (
            SeriesPage(
                series=data["title"],
                alt_titles=[],
                alt_titles_str=None,
                slug=data["slug"],
                cover_vol_url=data["cover"],
                metadata=[],
                synopsis=data["description"],
                author=data["author"],
                chapter_list=data["chapter_list"],
                original_url=data["original_url"],
            )
            if data
            else None
        )
