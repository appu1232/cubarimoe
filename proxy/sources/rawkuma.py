import re
import ast

from bs4 import BeautifulSoup
from bs4.element import NavigableString
from django.shortcuts import redirect
from django.urls import re_path

from ..source import ProxySource
from ..source.data import ChapterAPI, ProxyException, SeriesAPI, SeriesPage
from ..source.helpers import api_cache, get_wrapper

class Rawkuma(ProxySource):
    def get_reader_prefix(self):
        return "rawkuma"

    def shortcut_instantiator(self):
        def handler(request, raw_url):
            slug_name = self.get_slug_name(self.normalize_slug(raw_url))
            canonical_chapter = self.parse_chapter(raw_url).replace(".", "-")
            if canonical_chapter:
                return redirect(
                    f"reader-{self.get_reader_prefix()}-chapter-page",
                    slug_name,
                    canonical_chapter,
                    "1",
                )
            else:
                return redirect(
                    f"reader-{self.get_reader_prefix()}-series-page",
                    slug_name,
                )

        return [ re_path(r"^rk/(?P<raw_url>[\w\d\/:.-]+)", handler) ]

    @staticmethod
    def normalize_slug(denormal):
        normal = re.split(r'-chapter-\d*', denormal.strip('/'))[0]
        normal = 'https://' + re.sub(r'https?:\/\/', '', normal)
        return normal

    @staticmethod
    def get_slug_name(url):
        return url.strip("/").split("/")[-1]

    @staticmethod
    def get_series_url(meta_id):
        return "https://rawkuma.com/manga/" + meta_id

    @staticmethod
    def parse_chapter(raw_url):
        search = re.search(r'chapter-([\d-]+)$', raw_url.strip("/"))
        if not search: return ""
        return search.group(1).replace("-", ".")

    def rk_scrape_common(self, meta_id):
        resp = get_wrapper(self.get_series_url(meta_id))
        if resp.status_code != 200: return None

        data = resp.text
        soup = BeautifulSoup(data, "html.parser")

        try:
            title = soup.title.text.split('– Rawkuma')[0].strip()
        except AttributeError:
            return None
        
        # Default values
        author = "None"
        artist = ""
        description = "No description."
        cover = ""
        
        try:
            parsed_author = author
            parsed_artist = artist
            for element in soup.select('div.infox > div > div.fmed > b'):
                if element.text.strip() == 'Author':
                    parsed_author = element.next_sibling.next_sibling.text.strip()  # Need two next_siblings because one gives the '\n' between elements
                elif element.text.strip() == 'Artist':
                    parsed_artist = element.next_sibling.next_sibling.text.strip()
            author = parsed_author
            artist = parsed_artist
        except AttributeError:
            pass
        if not artist: artist = author

        try:
            parsed_desc = ""
            paragraphs = soup.select_one('div.infox > div > div[itemprop="description"]').descendants
            for element in paragraphs:
                if type(element) == NavigableString and element.parent.name != 'a':
                    parsed_desc += str(element)
            description = parsed_desc
        except AttributeError:
            pass

        try:
            parsed_cover = ""
            for element in soup.find_all("div", class_="thumb")[0].children:
                if element.name == 'img':
                    parsed_cover = 'https://' + re.sub(r'^(https?:)?\/\/', '', element['src'])
            cover = parsed_cover
        except AttributeError:
            pass

        groups_dict = {"1": "N/A"}

        chapter_list = []
        chapter_dict = {}
        chapters = list(
            map(
                lambda a: [
                    a.text,
                    a.parent["href"],
                    a.next_sibling.next_sibling.text
                ],
                soup.find_all("span", class_="chapternum")
            )
        )
        for chapter in chapters:
            canonical_chapter = self.parse_chapter(chapter[1])
            chapter_list.append(
                [
                    "",
                    canonical_chapter,
                    chapter[0],
                    canonical_chapter.replace(".", "-"),
                    "N/A",
                    chapter[2],
                    "",
                ]
            )
            chapter_dict[canonical_chapter] = {
                "volume": "1",
                "title": chapter[0],
                "groups": { "1": self.wrap_chapter_meta(self.get_slug_name(chapter[1])) },
            }
        

        return {
            "slug": meta_id,
            "title": title,
            "description": description,
            "series": title,
            "alt_titles_str": None,
            "cover_vol_url": cover,
            "metadata": [],
            "author": author,
            "artist": artist,
            "groups": groups_dict,
            "cover": cover,
            "chapter_dict": chapter_dict,
            "chapter_list": chapter_list,
        }

    @api_cache(prefix="rk_series_dt", time=600)
    def series_api_handler(self, meta_id):
        data = self.rk_scrape_common(meta_id)
        if not data: return None

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

    @api_cache(prefix="rk_chapter_dt", time=3600)
    def chapter_api_handler(self, chapter_meta_id):
        chapter_url = "https://rawkuma.com/" + chapter_meta_id
        resp = get_wrapper(chapter_url)
        if resp.status_code != 200: return None

        data = resp.text
        search = re.search(r'"images"\s?:\s?\[[^]]*\]', data)
        if search is None:
            raise ProxyException("Can't decode image array.")

        str_pages = re.split(re.compile(r'"images"\s?:\s?'), search.group(0))[1]
        pages = ast.literal_eval(str_pages)
        return ChapterAPI(pages=pages, series=chapter_meta_id, chapter="")

    @api_cache(prefix="rk_series_page_dt", time=600)
    def series_page_handler(self, meta_id):
        data = self.rk_scrape_common(meta_id)
        if not data: return None

        original_url = self.get_series_url(meta_id)
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
