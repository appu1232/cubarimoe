# from .sources.foolslide import FoolSlide
import imp
from proxy.sources.dynasty import Dynasty
from .sources.imgbb import Imgbb
from .sources.imgur import Imgur
# from .sources.mangabox import MangaBox
from .sources.mangadex import MangaDex
from .sources.nhentai import NHentai
from .sources.readmanhwa import ReadManhwa
# from .sources.hitomi import Hitomi
from .sources.gist import Gist
from .sources.mangakatana import MangaKatana
from .sources.nepnep import NepNep
from .sources.imgbox import Imgbox
from .sources.imgchest import ImageChest
from .sources.reddit import Reddit
from .sources.mangadventure import MangAdventure
from .sources.dynasty import Dynasty
from .sources.catbox import Catbox
from .sources.rawkuma import Rawkuma

sources = [
    MangaDex(),
    NHentai(),
    # FoolSlide(),
    MangAdventure(),
    ReadManhwa(),
    Imgur(),
    # MangaBox(),
    # Hitomi(),
    Gist(),
    MangaKatana(),
    NepNep(),
    Imgbox(),
    ImageChest(),
    Reddit(),
    Imgbb(),
    Dynasty(),
    Catbox(),
    Rawkuma(),
]
