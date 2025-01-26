import re

from bs4 import BeautifulSoup
from django.shortcuts import redirect
from django.urls import re_path

from ..source import ProxySource
from ..source.data import ChapterAPI, SeriesAPI, SeriesPage
from ..source.helpers import api_cache, get_wrapper


class NepNep(ProxySource):
    def get_reader_prefix(self):
        return "weebcentral"

    def shortcut_instantiator(self):
        def handler(request, raw_url):
            if "/chapters/" in raw_url:
                slug_name = self.get_slug_name_with_chapter_url(raw_url)
                data = self.nn_scrape_common(slug_name)
                canonical_chapter = data["chapter_id_map"][raw_url.split(
                    "/")[-1]]
                return redirect(
                    f"reader-{self.get_reader_prefix()}-chapter-page",
                    slug_name,
                    canonical_chapter,
                    "1",
                )
            elif "/series/" in raw_url:
                return redirect(
                    f"reader-{self.get_reader_prefix()}-series-page",
                    self.get_slug_name(raw_url),
                )

        return [
            re_path(r"^wc/(?P<raw_url>[\w\d\/:.-]+)", handler),
        ]

    @staticmethod
    def get_slug_name(normalized_url):
        return normalized_url.split("/")[-2]

    @staticmethod
    def get_slug_name_with_chapter_url(chapter_url):
        # An extra call here, can be optimised
        url = 'https://weebcentral.com/chapters/' + chapter_url.split("/")[-1]
        resp = get_wrapper(url)
        if resp.status_code == 200:
            pattern = r'\'series_id\'\s*:\s*\'([A-Z0-9]+)\''
            match = re.search(pattern, resp.text)
            series_id = match.group(1)
            return series_id

    @api_cache(prefix="nn_common_scrape_dt", time=600)
    def nn_scrape_common(self, meta_id):
        series_url = 'https://weebcentral.com/series/' + meta_id
        chapter_list_url = 'https://weebcentral.com/series/' + \
            meta_id + "/full-chapter-list"
        series_resp = get_wrapper(series_url)
        chapter_list_resp = get_wrapper(chapter_list_url)
        if series_resp.status_code == 200 and chapter_list_resp.status_code == 200:
            series_resp_data = series_resp.text
            chapter_list_resp_data = chapter_list_resp.text
            series_resp_soup = BeautifulSoup(series_resp_data, "html.parser")
            chapter_list_resp_soup = BeautifulSoup(
                chapter_list_resp_data, "html.parser")
            try:
                title = series_resp_soup.find("h1").text
            except AttributeError:
                return None

            author = "None"
            description = "No Description."
            author_elements = series_resp_soup.select(
                "ul > li:has(strong:-soup-contains(Author)) > span > a")
            description_element = series_resp_soup.select_one(
                "li:has(strong:-soup-contains(Description)) > p")
            if author_elements:
                author = ", ".join([link.get_text(strip=True)
                                   for link in author_elements])
            if description_element:
                description = description_element.get_text(strip=True)
            try:
                cover = series_resp_soup.select_one(
                    "section[x-data] > section").select_one("img").attrs["src"]
            except IndexError:
                cover = ""
            groups_dict = {"1": "WeebCentral"}
            chapter_id_map = {}
            chapter_list = []
            chapter_dict = {}

            chapter_list_data = chapter_list_resp_soup.select(
                "div[x-data] > a")
            for ch, chapter in enumerate(chapter_list_data):
                name = chapter.select_one("span.flex > span").get_text()
                date = "No date."
                try:
                    date = chapter.select_one(
                        "time[datetime]").get_text().split("T")[0]
                except:
                    pass
                url = chapter.attrs["href"]
                chapter_dict[str(len(chapter_list_data) - ch)] = {
                    "volume": "NA",
                    "title": name,
                    "groups": {"1": self.wrap_chapter_meta(url.split("/")[-1])},
                    "date": date
                }
                chapter_id_map[url.split(
                    "/")[-1]] = len(chapter_list_data) - ch

            chapter_list = [
                [
                    ch[0],
                    ch[0],
                    ch[1]["title"],
                    ch[0],
                    "Multiple Groups"
                    if len(ch[1]["groups"]) > 1
                    else groups_dict[list(ch[1]["groups"].keys())[0]],
                    ch[1]["date"],
                    ch[1]["volume"],
                ]
                for ch in sorted(
                    chapter_dict.items(),
                    key=lambda m: int(m[0]),
                    reverse=True,
                )
            ]

            return {
                "slug": meta_id,
                "title": title,
                "description": description,
                "series": title,
                "alt_titles_str": None,
                "cover_vol_url": cover,
                "metadata": [],
                "author": author,
                "artist": author,
                "groups": groups_dict,
                "cover": cover,
                "chapter_dict": chapter_dict,
                "chapter_list": chapter_list,
                "chapter_id_map": chapter_id_map
            }
        else:
            return None

    def series_api_handler(self, meta_id):
        data = self.nn_scrape_common(meta_id)
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
        else:
            return None

    @api_cache(prefix="nn_chapter_dt", time=3600)
    def chapter_api_handler(self, meta_id):
        url = 'https://weebcentral.com/chapters/' + meta_id + \
            "/images?is_prev=False&current_page=1&reading_style=long_strip"
        resp = get_wrapper(url)
        images = []
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, "html.parser")
            images_elements = soup.select("img")
            for el in images_elements:
                images.append(el.attrs["src"])
            return ChapterAPI(pages=images, series=meta_id, chapter="")
        else:
            return None

    def series_page_handler(self, meta_id):
        data = self.nn_scrape_common(meta_id)
        original_url = 'https://weebcentral.com/series/' + meta_id

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
                original_url=original_url,
            )
        else:
            return None
