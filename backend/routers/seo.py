"""robots.txt và sitemap.xml cho máy tìm kiếm (Google, Bing, Cốc Cốc)."""

from fastapi import APIRouter, Request
from fastapi.responses import PlainTextResponse, Response

from core import config  # noqa: F401
from core import seo

router = APIRouter(include_in_schema=False)


@router.get("/robots.txt")
def robots(request: Request):
    return PlainTextResponse(seo.robots_txt(seo.goc_cong_khai(request.scope)), headers={"Cache-Control": "public, max-age=3600"})


@router.get("/sitemap.xml")
def sitemap(request: Request):
    return Response(seo.sitemap_xml(seo.goc_cong_khai(request.scope)), media_type="application/xml",
                    headers={"Cache-Control": "public, max-age=3600"})
