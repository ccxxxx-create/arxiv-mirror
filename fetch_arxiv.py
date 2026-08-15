#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""抓取 arXiv 论文 → 生成 arxiv/latest.json（供前端绕过 CORS 直读）。

由 GitHub Actions 定时运行，把结果提交回仓库 arxiv/latest.json。
前端（个人工作台「科研」页）读取：
  https://raw.githubusercontent.com/<用户名>/<仓库名>/main/arxiv/latest.json
"""
import json
import os
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

API = "https://export.arxiv.org/api/query"

# 无人机方向
UAV_QUERY = 'all:"unmanned aerial vehicle" OR all:UAV OR all:drone OR all:"aerial robotics" OR all:"urban air mobility"'

# 整体前沿：跨学科各取 1 篇
GENERAL_NAMES = {
    "cs.AI": "人工智能",
    "physics.gen-ph": "物理",
    "q-bio.QM": "生物",
    "q-fin.GN": "金融",
    "econ.GN": "经济",
    "stat.ML": "统计",
    "math.GM": "数学",
}
GENERAL_QUERY = " OR ".join("cat:" + c for c in GENERAL_NAMES)


def strip_html(s):
    s = re.sub(r"<[^>]+>", " ", s or "")
    s = s.replace("&nbsp;", " ").replace("&amp;", "&").replace("&lt;", "<")
    s = s.replace("&gt;", ">").replace("&quot;", '"').replace("&#39;", "'")
    return re.sub(r"\s+", " ", s).strip()


def query(search_query, max_results=10):
    url = API + "?search_query=" + urllib.parse.quote(search_query) + \
          "&start=0&max_results=%d&sortBy=submittedDate&sortOrder=descending" % max_results
    req = urllib.request.Request(url, headers={"User-Agent": "workbench-arxiv-mirror/1.0"})
    with urllib.request.urlopen(req, timeout=40) as resp:
        return resp.read().decode("utf-8")


def parse_entries(xml_text):
    ns = {"a": "http://www.w3.org/2005/Atom"}
    root = ET.fromstring(xml_text)
    out = []
    for entry in root.findall("a:entry", ns):
        def txt(tag):
            node = entry.find("a:" + tag, ns)
            return node.text if node is not None and node.text else ""

        title = strip_html(txt("title"))
        summary = strip_html(txt("summary"))
        link = ""
        for l in entry.findall("a:link", ns):
            if l.get("rel") == "alternate":
                link = l.get("href") or ""
                break
        if not link:
            idnode = entry.find("a:id", ns)
            link = idnode.text if idnode is not None else ""

        catnode = entry.find("a:category", ns)
        category = catnode.get("term") or "" if catnode is not None else ""
        published = txt("published")
        if title:
            out.append({
                "title": title,
                "summary": summary,
                "link": link,
                "published": published,
                "category": category,
            })
    return out


def pick_general(entries):
    picked = []
    seen = set()
    for e in entries:
        cat = e.get("category") or ""
        main = next((g for g in GENERAL_NAMES if cat.startswith(g)), None)
        if main and main not in seen:
            seen.add(main)
            e2 = dict(e)
            e2["category"] = main
            picked.append(e2)
    return picked


def main():
    uav = []
    general = []
    try:
        uav = parse_entries(query(UAV_QUERY, 10))
    except Exception as exc:
        print("UAV fetch failed:", exc)
    try:
        general = pick_general(parse_entries(query(GENERAL_QUERY, 50)))
    except Exception as exc:
        print("General fetch failed:", exc)

    now = datetime.now(timezone.utc)
    data = {
        "date": now.strftime("%Y%m%d"),
        "updated": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "uav": uav,
        "general": general,
    }
    os.makedirs("arxiv", exist_ok=True)
    with open("arxiv/latest.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print("Wrote arxiv/latest.json: uav=%d general=%d" % (len(uav), len(general)))


if __name__ == "__main__":
    main()
