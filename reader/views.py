from django.shortcuts import render, get_object_or_404
from django.http import HttpResponse
from django.conf import settings
from django.http import HttpResponseNotFound
from django.views.generic import DetailView, TemplateView
from django.views.decorators.cache import cache_page
from django.core.cache import cache
from django.db.models import F
from django.contrib.contenttypes.models import ContentType
from .models import HitCount, Series, Volume, Chapter
from datetime import datetime, timedelta, timezone
from .users_cache_lib import curr_user_and_online
from collections import defaultdict
import os
import json


def hit_count(request):
    if request.POST:
        ### Install and test with memcache first
        user_ip = curr_user_and_online(request)
        page_id = f"url_{request.POST['series']}/{request.POST['chapter'] if 'chapter' in request.POST else ''}{user_ip}"
        page_hits_cache = f"url_{request.POST['series']}/{request.POST['chapter'] if 'chapter' in request.POST else ''}"
        cache.set(page_id, page_id, 60)

        page_cached_users = cache.get(page_hits_cache)
        print("page_cached_users", page_cached_users)
        if page_cached_users:
            page_cached_users = [ip for ip in page_cached_users if cache.get(ip)]
        else:
            page_cached_users = []
        if user_ip not in page_cached_users:
            page_cached_users.append(user_ip)
            series_slug = request.POST["series"]
            series_id = Series.objects.get(slug=series_slug).id
            series = ContentType.objects.get(app_label='reader', model='series')
            hit, _ = HitCount.objects.get_or_create(content_type=series, object_id=series_id)
            hit.hits = F('hits') + 1
            hit.save()
            if "chapter" in request.POST:
                chapter_number = request.POST["chapter"]
                group_id = request.POST["group"]
                chapter = ContentType.objects.get(app_label='reader', model='chapter')
                hit, _ = HitCount.objects.get_or_create(content_type=chapter, object_id=Chapter.objects.get(chapter_number=float(chapter_number), group__id=group_id, series__id=series_id).id)
                hit.hits = F('hits') + 1
                hit.save()
        
        print("page_cached_users new", page_cached_users)
        cache.set(page_hits_cache, page_cached_users)
        print(page_hits_cache)
        # page_cached_users = cache.get(page_hits_cache)
        # print("page_hits_cache new 2", page_cached_users)

        
        return HttpResponse(json.dumps({}), content_type='application/json')


def get_chapter_time(chapter):
    upload_date = chapter.uploaded_on
    upload_time = (datetime.utcnow().replace(tzinfo=timezone.utc) - upload_date).total_seconds()
    days = int(upload_time // (24 * 3600))
    upload_time = upload_time % (24 * 3600)
    hours = int(upload_time // 3600)
    upload_time %= 3600
    minutes = int(upload_time // 60)
    upload_time %= 60
    seconds = int(upload_time)
    if days == 0 and hours == 0 and minutes == 0:
        upload_date = f"{seconds} second{'s' if seconds != 1 else ''} ago"
    elif days == 0 and hours == 0:
        upload_date = f"{minutes} min{'s' if minutes != 1 else ''} ago"
    elif days == 0:
        upload_date = f"{hours} hour{'s' if hours != 1 else ''} ago"
    elif days < 7:
        upload_date = f"{days} day{'s' if days != 1 else ''} ago"
    else:
        upload_date = upload_date.strftime("%Y-%m-%d")
    return upload_date


def series_info(request, series_slug):
    cache_request = cache.get(f"series_page_{series_slug}")
    if not cache_request:
        series = get_object_or_404(Series, slug=series_slug)
        chapters = Chapter.objects.filter(series=series)
        latest_chapter = chapters.latest('uploaded_on')
        vols = Volume.objects.filter(series=series).order_by('-volume_number')
        cover_vol_url = ""
        for vol in vols:
            if vol.volume_cover:
                cover_vol_url = f"/media/{vol.volume_cover}"
                break
        content_series = ContentType.objects.get(app_label='reader', model='series')
        hit, _ = HitCount.objects.get_or_create(content_type=content_series, object_id=series.id)
        chapter_list = []
        volume_dict = defaultdict(list)
        for chapter in chapters:
            # upload_date = chapter.get_chapter_time()
            u = chapter.uploaded_on
            chapter_list.append([chapter.clean_chapter_number(), chapter.title, chapter.slug_chapter_number(), chapter.group.name, [u.year, u.month-1, u.day, u.hour, u.minute, u.second], chapter.volume])
            volume_dict[chapter.volume].append([chapter.clean_chapter_number(), chapter.slug_chapter_number(), chapter.group.name, [u.year, u.month-1, u.day, u.hour, u.minute, u.second]])
        volume_list = []
        for key, value in volume_dict.items():
            volume_list.append([key, sorted(value, key=lambda x: float(x[0]), reverse=True)])
        chapter_list.sort(key=lambda x: float(x[0]), reverse=True)
        cache_request = {
                "series": series.name,
                "series_id": series.id,
                "slug": series.slug,
                "cover_vol_url": cover_vol_url,
                "views": hit.hits + 1,
                "synopsis": series.synopsis, 
                "author": series.author.name,
                "artist": series.artist.name,
                "last_added": [latest_chapter.clean_chapter_number(), latest_chapter.uploaded_on],
                "chapter_list": chapter_list,
                "volume_list": sorted(volume_list, key=lambda m: m[0], reverse=True)
        }
        cache.set(f"series_page_{series_slug}", cache_request, 3600 * 12)
    cache_request["is_mod"] = request.user.is_staff
    return render(request, 'reader/series_info.html', cache_request)


@cache_page(600)
def reader(request, series_slug, chapter, page):
    return render(request, 'reader/reader.html', {})
