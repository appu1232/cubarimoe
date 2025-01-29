import re
from datetime import datetime

from bs4 import BeautifulSoup
from django.shortcuts import redirect
from django.urls import re_path

from ..source import ProxySource
from ..source.data import ChapterAPI, SeriesAPI, SeriesPage
from ..source.helpers import api_cache, get_wrapper

class Dynasty(ProxySource):
    def get_reader_prefix(self):
        return "dynasty"
    
    def shortcut_instantiator(self):
        def handler(request, raw_url):
            if "/chapters/" in raw_url:
                try:
                    canonical_chapter = self.parse_chapter(raw_url)
                    slug_name = self.get_slug_name(self.normalize_slug(raw_url))
                except ValueError:
                    # attempt to fetch the series name, otherwise fall back to the full slug
                    chapter_url = raw_url + ".json"
                    resp = get_wrapper(chapter_url)
                    if resp.status_code == 200:
                        data = resp.json()
                        series_slug = next(
                            (tag["permalink"] for tag in data["tags"] if tag["type"] == "Series"),
                            None
                        )
                        if series_slug is None:
                            # eg. https://dynasty-scans.com/chapters/wanna_sip
                            slug_name = self.get_slug_name(raw_url)
                            canonical_chapter = "1"
                        else:
                            # eg. https://dynasty-scans.com/chapters/bloom_into_you_volume_1_extras
                            slug_name = series_slug
                            canonical_chapter = self.get_slug_name(raw_url).replace(
                                series_slug + "_", ""
                            )
                    else:
                        return None
                
                print(slug_name, canonical_chapter)
                return redirect(
                    f"reader-{self.get_reader_prefix()}-chapter-page",
                    slug_name,
                    canonical_chapter,
                    "1",
                )
            else:
                return redirect(
                    f"reader-{self.get_reader_prefix()}-series-page",
                    self.get_slug_name(self.normalize_slug(raw_url)),
                )
        
        return [re_path(r"^ds/(?P<raw_url>[\w\d\/:.-]+)", handler)]
    
    @staticmethod
    def normalize_slug(denormal):
        if "/chapters/" in denormal:
            copy = denormal
            denormal = denormal.split("/")
            if copy.startswith("http"):
                denormal.pop(0)
            denormal[-1] = "_".join(denormal[-1].split("_")[:-1])
            denormal = "https:/" + "/".join(denormal)
            denormal = denormal.replace("/chapters/", "/series/")
        return denormal
    
    @staticmethod
    def get_slug_name(normalized_url):
        return normalized_url.split("/")[-1]
    
    @staticmethod
    def parse_chapter(raw_url):
        int(raw_url.rsplit("ch")[-1])
        return raw_url.rsplit("ch")[-1].replace("_", ".")
    
    @staticmethod
    def parse_date(date):
        date_format = "%Y-%m-%d"
        output_date_format = "%d-%m-%Y"
        return datetime.strptime(
            date,
            date_format,
        ).strftime(output_date_format)
    
    def ds_api_common(self, meta_id):
        base_url = "https://dynasty-scans.com"
        series_url = f"https://dynasty-scans.com/series/{meta_id}.json"
        resp = get_wrapper(series_url)
        if resp.status_code == 200:
            data = resp.json()
            
            original_url = f"https://dynasty-scans.com/series/{meta_id}"
            title = data["name"]
            alt_titles = data["aliases"]
            
            if data["description"] is not None:
                soup = BeautifulSoup(data["description"], "html.parser")
                description = soup.get_text("\n").strip()
            else:
                description = "No description."
            
            author = next(
                (tag["name"] for tag in data["tags"] if tag["type"] == "Author"), "Unknown"
            )
            
            if data["cover"] is not None:
                cover = base_url + data["cover"]
            else:
                cover = ""
            
            # fetch scanlation groups
            groups_dict = {}
            groups_map = {}
            group_index = 0
            for tagging in data["taggings"]:
                if "tags" in tagging:
                    groups = [tag["name"] for tag in tagging["tags"] if tag["type"] == "Scanlator"]
                    group = ", ".join(groups)
                    if group not in groups_map:
                        groups_dict[str(group_index)] = group
                        groups_map[group] = str(group_index)
                        group_index += 1
            
            chapter_list = []
            chapter_dict = {}
            volume = None
            
            for tagging in data["taggings"]:
                if "header" in tagging:
                    match = re.match(r"Volume (\d+)", tagging["header"])
                    if match is None:
                        volume = None
                    else:
                        volume = match.group(1)
                else:
                    try:
                        canonical_chapter = self.parse_chapter(tagging["permalink"])
                    except ValueError:
                        canonical_chapter = tagging["permalink"].replace(meta_id + "_", "")
                    chapter_title = tagging["title"]
                    upload_date = self.parse_date(tagging["released_on"])
                    groups = [tag["name"] for tag in tagging["tags"] if tag["type"] == "Scanlator"]
                    group = ", ".join(groups)
                    
                    chapter_list.append(
                        [
                        "",
                        canonical_chapter,
                        chapter_title,
                        canonical_chapter.replace(".", "-"),
                        group,
                        upload_date,
                        volume,
                        ]
                    )
                    
                    chapter_dict[canonical_chapter] = {
                        "volume": volume,
                        "title": chapter_title,
                        "groups":
                        {
                        groups_map[group]:
                        self.wrap_chapter_meta(self.get_slug_name(tagging["permalink"]))
                        },
                    }
            
            return {
                "slug": meta_id,
                "title": title,
                "description": description,
                "series": title,
                "alt_titles": alt_titles,
                "metadata": [],
                "author": author,
                "artist": author,
                "groups": groups_dict,
                "cover": cover,
                "chapter_dict": chapter_dict,
                "chapter_list": chapter_list,
                "original_url": original_url
            }
        else:
            # Oneshots
            chapter_url = f"https://dynasty-scans.com/chapters/{meta_id}.json"
            resp = get_wrapper(chapter_url)
            
            if resp.status_code == 200:
                data = resp.json()
                
                original_url = f"https://dynasty-scans.com/chapters/{meta_id}"
                title = data["title"]
                description = "No description."
                author = next(
                    (tag["name"] for tag in data["tags"] if tag["type"] == "Author"), "Unknown"
                )
                cover = base_url + data["pages"][0]["url"]
                upload_date = self.parse_date(data["released_on"])
                
                groups = [tag["name"] for tag in data["tags"] if tag["type"] == "Scanlator"]
                group = ", ".join(groups)
                groups_dict = {"1": group}
                
                chapter_list = [[
                    "",
                    "1",
                    title,
                    "1",
                    group,
                    upload_date,
                    "1",
                ]]
                
                chapter_dict = {
                    "1":
                    {
                    "volume": "1",
                    "title": title,
                    "groups": {
                    "1": self.wrap_chapter_meta(self.get_slug_name(data["permalink"]))
                    },
                    }
                }
                
                return {
                    "slug": meta_id,
                    "title": title,
                    "description": description,
                    "series": title,
                    "alt_titles": None,
                    "metadata": [],
                    "author": author,
                    "artist": author,
                    "groups": groups_dict,
                    "cover": cover,
                    "chapter_dict": chapter_dict,
                    "chapter_list": chapter_list,
                    "original_url": original_url
                }
            else:
                return None
    
    @api_cache(prefix="ds_series_dt", time=600)
    def series_api_handler(self, meta_id):
        data = self.ds_api_common(meta_id)
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
    
    @api_cache(prefix="ds_chapter_dt", time=3600)
    def chapter_api_handler(self, meta_id):
        base_url = "https://dynasty-scans.com"
        chapter_url = f"https://dynasty-scans.com/chapters/{meta_id}.json"
        resp = get_wrapper(chapter_url)
        if resp.status_code == 200:
            data = resp.json()
            pages = [base_url + page["url"] for page in data["pages"]]
            return ChapterAPI(pages=pages, series=meta_id, chapter=data["title"])
    
    @api_cache(prefix="ds_series_page_dt", time=600)
    def series_page_handler(self, meta_id):
        data = self.ds_api_common(meta_id)
        
        if data:
            return SeriesPage(
                series=data["title"],
                alt_titles=data["alt_titles"],
                alt_titles_str=None,
                slug=data["slug"],
                cover_vol_url=data["cover"],
                metadata=[],
                synopsis=data["description"],
                author=data["author"],
                chapter_list=data["chapter_list"],
                original_url=data["original_url"],
            )
        else:
            return None
