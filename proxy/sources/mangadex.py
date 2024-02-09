import asyncio
from concurrent.futures.thread import ThreadPoolExecutor
from datetime import datetime
import html
from typing import Dict, Optional, Union
from django.core.cache import cache

from django.http import HttpResponse
from django.shortcuts import redirect
from django.urls import re_path

from ..source import ProxySource
from ..source.data import ChapterAPI, ProxyException, SeriesAPI, SeriesPage
from ..source.helpers import api_cache, get_wrapper, post_wrapper
from ..source.markdown_parser import parse_html

SUPPORTED_LANG = "en"
GROUP_KEY = "scanlation_group"

CONTENT_RATINGS = "contentRating[]=safe&contentRating[]=suggestive&contentRating[]=erotica&contentRating[]=pornographic"

HEADERS_COMMON = {
    "Referer": "https://mangadex.org",
    "x-requested-with": "cubari",
    "User-Agent": "Cubari/1.0",
}


class MangaDex(ProxySource):
    def get_reader_prefix(self):
        return "mangadex"

    def shortcut_instantiator(self):
        async def legacy_mapper(series_id):
            try:
                series_id = int(series_id)
                resp = await post_wrapper(
                    f"https://api.mangadex.org/legacy/mapping",
                    json={"type": "manga", "ids": [series_id]},
                    headers=HEADERS_COMMON,
                    use_proxy=True,
                )
                if resp.status != 200:
                    raise Exception("Failed to translate ID.")
                return (await resp.json())["data"][0]["attributes"]["newId"]
            except ValueError:
                return series_id

        async def series(request, series_id):
            series_id = await legacy_mapper(series_id)
            return redirect(f"reader-{self.get_reader_prefix()}-series-page", series_id)

        async def series_chapter(request, series_id, chapter, page="1"):
            series_id = await legacy_mapper(series_id)
            return redirect(
                f"reader-{self.get_reader_prefix()}-chapter-page",
                series_id,
                chapter,
                page,
            )

        def chapter(request, chapter_id, page="1"):
            data = self.chapter_api_handler(chapter_id)
            if data:
                data = data.objectify()
                return redirect(
                    f"reader-{self.get_reader_prefix()}-chapter-page",
                    str(data["series"]),
                    str(data["chapter"]),
                    page,
                )
            else:
                return HttpResponse(status=500)

        return [
            re_path(r"^proxy/mangadex/(?P<series_id>[\d]{1,9})/$", series),
            re_path(
                r"^proxy/mangadex/(?P<series_id>[\d]{1,9})/(?P<chapter>[\d]{1,4})/$",
                series_chapter,
            ),
            re_path(
                r"^proxy/mangadex/(?P<series_id>[\d]{1,9})/(?P<chapter>[\d]{1,4})/(?P<page>[\d]{1,4})/$",
                series_chapter,
            ),
            re_path(r"^read/mangadex/(?P<series_id>[\d]{1,9})/$", series),
            re_path(
                r"^read/mangadex/(?P<series_id>[\d]{1,9})/(?P<chapter>[\d]{1,4})/$",
                series_chapter,
            ),
            re_path(
                r"^read/mangadex/(?P<series_id>[\d]{1,9})/(?P<chapter>[\d]{1,4})/(?P<page>[\d]{1,4})/$",
                series_chapter,
            ),
            re_path(r"^title/(?P<series_id>[\d\w\-]+)/$", series),
            re_path(r"^title/(?P<series_id>[\d\w\-]+)/([\w-]+)/$", series),
            re_path(r"^manga/(?P<series_id>[\d\w\-]+)/$", series),
            re_path(r"^manga/(?P<series_id>[\d\w\-]+)/([\w-]+)/$", series),
            re_path(r"^chapter/(?P<chapter_id>[\d\w\-]+)/$", chapter),
            re_path(
                r"^chapter/(?P<chapter_id>[\d\w\-]+)/(?P<page>[\d]{1,9})/$", chapter
            ),
        ]

    def process_description(self, desc):
        return parse_html(desc)

    def handle_oneshot_chapters(self, resp):
        """This expects a chapter API response object."""
        try:
            parse = (
                (lambda s: str(float(s)))
                if "." in resp["chapter"]
                else (lambda s: str(int(s)))
            )
            return parse(resp["chapter"]), parse(resp["chapter"])
        except ValueError:
            return "Oneshot", f"0.0{str(resp['timestamp'])}"

    @staticmethod
    def date_parser(timestamp):
        timestamp = int(timestamp)
        try:
            date = datetime.utcfromtimestamp(timestamp)
        except ValueError:
            date = datetime.utcfromtimestamp(timestamp // 1000)
        return [
            date.year,
            date.month - 1,
            date.day,
            date.hour,
            date.minute,
            date.second,
        ]

    @api_cache(prefix="md_common_dt", time=600)
    async def md_api_common(self, meta_id):
        current_offset = 0

        async def fetch_task(req):
            resp = await get_wrapper(req["url"], headers=HEADERS_COMMON, use_proxy=True)
            return {
                "type": req["type"],
                "res": resp,
            }

        result = await asyncio.gather(
            *map(
                lambda req: fetch_task(req),
                [
                    {
                        "type": "main",
                        "url": f"https://api.mangadex.org/manga/{meta_id}?includes[]=cover_art",
                    },
                    {
                        "type": "chapter",
                        "url": f"https://api.mangadex.org/manga/{meta_id}/feed?{CONTENT_RATINGS}&translatedLanguage[]={SUPPORTED_LANG}&limit=500&includeEmptyPages=0&includeFuturePublishAt=0&includeExternalUrl=0",
                    },
                ],
            )
        )

        main_data = None
        chapter_data = None

        for res in result:
            if res["res"].status != 200:
                raise ProxyException(
                    f"The MangaDex API failed to load. Got status code: {res['res'].status}"
                )
            if res["type"] == "main":
                main_data = await res["res"].json()
            elif res["type"] == "chapter":
                chapter_data = await res["res"].json()

        current_offset = 500
        if "total" in chapter_data and current_offset < chapter_data["total"]:
            unfetched_urls = []
            while current_offset < chapter_data["total"]:
                unfetched_urls.append(
                    f"https://api.mangadex.org/manga/{meta_id}/feed?{CONTENT_RATINGS}&translatedLanguage[]={SUPPORTED_LANG}&offset={current_offset}&limit=500"
                )
                current_offset = current_offset + 500

                results = await asyncio.gather(
                    *map(
                        lambda url: get_wrapper(
                            url=url,
                            headers=HEADERS_COMMON,
                            use_proxy=True,
                        ),
                        unfetched_urls,
                    )
                )

            for result in results:
                result_json = await result.json()
                chapter_data["data"].extend(result_json["data"])

        groups_set = {
            relationship["id"]
            for chapter in chapter_data["data"]
            for relationship in chapter["relationships"]
            if relationship["type"] == GROUP_KEY
        }

        resolved_groups_map = {}

        for group in groups_set:
            val = cache.get(group)
            if val:
                resolved_groups_map[group] = val

        # We need to make yet another call to get the scanlator
        # group names; we'll cache these names with a long TTL
        # since the CORS proxy doesn't handle the PHP array
        # syntax properly.
        remaining_groups = groups_set - set(resolved_groups_map)
        if len(remaining_groups):
            groups_api_url = f"https://api.mangadex.org/group?limit=100"
            for group in remaining_groups:
                groups_api_url += f"&ids[]={group}"
            groups_resp = await get_wrapper(groups_api_url, headers=HEADERS_COMMON)
            if groups_resp.status != 200:
                return
            for result in (await groups_resp.json())["data"]:
                group_id = result["id"]
                group_name = result["attributes"]["name"]
                resolved_groups_map[group_id] = group_name
                cache.set(group_id, group_name, 60 * 60 * 24)  # 24 hour cache

        groups_dict = {}
        groups_map = {}

        for key, value in enumerate(groups_set):
            groups_dict[str(key)] = resolved_groups_map[value]
            groups_map[value] = str(key)

        chapter_dict = {}

        oneshots = 0

        for chapter in chapter_data["data"]:
            chapter_id = chapter["id"]
            chapter_number = chapter["attributes"]["chapter"]
            chapter_title = chapter["attributes"]["title"]
            chapter_volume = chapter["attributes"]["volume"]
            chapter_timestamp = datetime.strptime(
                chapter["attributes"]["createdAt"], "%Y-%m-%dT%H:%M:%S%z"
            ).timestamp()
            chapter_group = None

            if not chapter_number:
                chapter_number = f"0.{oneshots}"
                oneshots += 1

            for relationship in chapter["relationships"]:
                if relationship["type"] == GROUP_KEY:
                    chapter_group = relationship["id"]
                    break

            # Bandaid fix but it should resolve most resolution issues
            if chapter_group is None:
                for relationship in chapter["relationships"]:
                    if relationship["type"] == "user":
                        chapter_group = relationship["id"]
                        break
                # If at this point it still doesn't have a group, fail the processing
                if chapter_group is None:
                    raise ProxyException(
                        "A chapter is missing a scanlator or user uploader."
                    )
                groups_set.add(chapter_group)
                groups_dict[str(len(groups_set))] = chapter_group
                groups_map[chapter_group] = str(len(groups_set))

            if chapter_number in chapter_dict:
                chapter_obj = chapter_dict[chapter_number]
                if not chapter_obj["title"]:
                    chapter_obj["title"] = chapter_title
                if not chapter_obj["volume"]:
                    chapter_obj["volume"] = chapter_volume
                if chapter_timestamp > chapter_obj["last_updated"]:
                    chapter_obj["last_updated"] = chapter_timestamp
                chapter_dict[chapter_number]["groups"][
                    groups_map[chapter_group]
                ] = self.wrap_chapter_meta(chapter_id)
                chapter_dict[chapter_number]["release_date"][
                    groups_map[chapter_group]
                ] = chapter_timestamp
            else:
                chapter_dict[chapter_number] = {
                    "volume": chapter_volume,
                    "title": chapter_title,
                    "groups": {
                        groups_map[chapter_group]: self.wrap_chapter_meta(chapter_id)
                    },
                    "release_date": {groups_map[chapter_group]: chapter_timestamp},
                    "last_updated": chapter_timestamp,
                }

        chapter_list = [
            [
                ch[0],
                ch[0],
                ch[1]["title"],
                ch[0].replace(".", "-"),
                "Multiple Groups"
                if len(ch[1]["groups"]) > 1
                else groups_dict[list(ch[1]["groups"].keys())[0]],
                "No date."
                if not ch[1]["last_updated"]
                else self.date_parser(ch[1]["last_updated"]),
                ch[1]["volume"] or "Unknown",
            ]
            for ch in sorted(
                chapter_dict.items(),
                key=lambda m: float(
                    ".".join(str(m[0]).split(".")[:2])
                    + "".join(str(m[0]).split(".")[2:])
                ),  # To get around weird chapter numbering like 21.15.1..
                reverse=True,
            )
        ]

        cover_filename = None
        for data in main_data["data"]["relationships"]:
            if data["type"] == "cover_art":
                cover_filename = data["attributes"]["fileName"]

        title: str = "Couldn't Resolve Title"
        title_metadata: Dict[str, str] = {
            **{
                k: v
                for alt_title in main_data["data"]["attributes"].get("altTitles", [])
                for k, v in alt_title.items()
            },
            **main_data["data"]["attributes"].get("title", {}),
        }
        for title_precedence in [SUPPORTED_LANG, "jp", "fr"]:
            if title_precedence in title_metadata:
                title = title_metadata[title_precedence]
                break

        description_object: Union[list, Dict[str, str]] = main_data["data"][
            "attributes"
        ]["description"]
        description: str = (
            description_object.get(SUPPORTED_LANG, "No English description.")
            if len(description_object)
            else "No description."
        )

        return {
            "slug": meta_id,
            "title": title,
            "description": description,
            "author": "",
            "artist": "",
            "groups": groups_dict,
            "chapter_dict": chapter_dict,
            "chapter_list": chapter_list,
            "cover": f"https://uploads.mangadex.org/covers/{meta_id}/{cover_filename}",
        }

    @api_cache(prefix="md_series_dt", time=600)
    async def series_api_handler(self, meta_id):
        data = await self.md_api_common(meta_id)
        if data:
            return SeriesAPI(
                slug=data["slug"],
                title=data["title"],
                description=data["description"],
                author=data["author"],
                artist=data["artist"],
                groups=data["groups"],
                cover=data["cover"],
                chapters=data["chapter_dict"],
            )

    @api_cache(prefix="md_chapter_dt", time=300)
    async def chapter_api_handler(self, meta_id):
        at_home: str = "at-home"
        chapter: str = "chapter"

        async def fetch_task(req):
            return {
                "type": req["type"],
                "res": await get_wrapper(
                    req["url"], headers=HEADERS_COMMON, use_proxy=True
                ),
            }

        result = await asyncio.gather(
            *map(
                lambda req: fetch_task(req),
                [
                    {
                        "type": at_home,
                        "url": f"https://api.mangadex.org/at-home/server/{meta_id}?forcePort443=true",
                    },
                    {
                        "type": chapter,
                        "url": f"https://api.mangadex.org/chapter/{meta_id}",
                    },
                ],
            )
        )

        at_home_data: Optional[Dict[str, str]] = None
        chapter_data: Optional[Dict[str, str]] = None
        for res in result:
            if res["res"].status != 200:
                raise ProxyException(
                    f"The MangaDex API failed to load. Got status code: {res['res'].status}"
                )
            if res["type"] == at_home:
                at_home_data = await res["res"].json()
            elif res["type"] == chapter:
                chapter_data = await res["res"].json()

        pages = [
            f"{at_home_data['baseUrl']}/data/{at_home_data['chapter']['hash']}/{page}"
            for page in at_home_data["chapter"]["data"]
        ]
        series = None
        chapter = chapter_data["data"]["attributes"]["chapter"]
        for relationship in chapter_data["data"]["relationships"]:
            if relationship["type"] == "manga":
                series = relationship["id"]
                break

        return ChapterAPI(pages=pages, series=series, chapter=chapter)

    @api_cache(prefix="md_series_page_dt", time=600)
    async def series_page_handler(self, meta_id):
        data = await self.md_api_common(meta_id)
        if data:
            return SeriesPage(
                series=data["title"],
                alt_titles=[],
                alt_titles_str=None,
                slug=data["slug"],
                cover_vol_url=data["cover"],
                metadata=[],
                synopsis=data["description"],
                author=data["artist"],
                chapter_list=data["chapter_list"],
                original_url=f"https://mangadex.org/title/{data['slug']}",
            )
