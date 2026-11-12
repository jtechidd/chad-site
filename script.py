import argparse
import json
import re
import shutil
import subprocess
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

import frontmatter
import sass
from dotenv import load_dotenv
from jinja2 import Environment, FileSystemLoader
from loguru import logger
from marko import Markdown
from marko.block import BlockElement
from marko.helpers import MarkoExtension
from marko.inline import Image, InlineElement, RawText

load_dotenv()

current_dir = Path(__file__).resolve().parent

src_dir = current_dir.joinpath("src")
assets_dir = src_dir.joinpath("assets")
assets_css_dir = assets_dir.joinpath("css")
assets_images_dir = assets_dir.joinpath("images")
assets_js_dir = assets_dir.joinpath("js")
posts_dir = src_dir.joinpath("posts")
templates_dir = src_dir.joinpath("templates")

dist_dir = current_dir.joinpath("dist")
dist_assets_dir = dist_dir.joinpath("assets")
dist_assets_css_dir = dist_assets_dir.joinpath("css")
dist_assets_images_dir = dist_assets_dir.joinpath("images")
dist_assets_js_dir = dist_assets_dir.joinpath("js")
dist_assets_data_dir = dist_assets_dir.joinpath("data")
dist_posts_dir = dist_dir.joinpath("posts")

# config
cf_page_proj = "chad-site"
bmc_link = "https://buymeacoffee.com/windriftz"
working_email = "windriftz.online@gmail.com"
featured_post_slugs = ["01-welcome-to-site"]
platforms = [
    {
        "name": "github",
        "link": "",
    },
    {
        "name": "youtube",
        "link": "",
    },
    {
        "name": "instagram",
        "link": "",
    },
    {
        "name": "bluesky",
        "link": "",
    },
    {
        "name": "substack",
        "link": "",
    },
    {
        "name": "mastodon",
        "link": "",
    },
]

jj2_env = Environment(loader=FileSystemLoader(templates_dir))
base_render_ctx = {"current_year": datetime.now().year}


class NoGivenTemplateException(Exception):
    pass


class PostSlugDuplication(Exception):
    pass


@contextmanager
def ensure_dir_and_open_file(path):
    parent = path.parent
    parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as file:
        yield file


def build_page(dest_path, template_path=None, template=None, context=None):
    if not template_path and not template:
        raise NoGivenTemplateException()
    if template_path:
        template = jj2_env.get_template(template_path)
    with ensure_dir_and_open_file(dest_path) as file:
        rendered = template.render() if context is None else template.render(context)
        file.write(rendered)


def walk_ast(ctx, element):
    if isinstance(element, (Image, ImageWithJsonAttr)):
        alt = element.children[0].children
        url = element.dest
        title = element.title
        no_track = False
        if isinstance(element, ImageWithJsonAttr) and element.attrs.get("no_track"):
            no_track = True
        if not no_track:
            ctx.get("images").append(
                {"url": url, "alt": alt, "title": title, "page_url": ctx["page_url"]}
            )
    text_blocks = ctx.get("text_blocks")
    text_blocks_len = len(text_blocks)
    if isinstance(element, BlockElement):  # noqa: SIM102
        if text_blocks_len == 0 or text_blocks[-1] != "":
            text_blocks.append("")
    if isinstance(element, RawText):  # noqa: SIM102
        if text_blocks_len > 0 and isinstance(text_blocks[-1], str):
            text_blocks[-1] += element.children
    if hasattr(element, "children"):
        for child in element.children:
            walk_ast(ctx, child)


class ImageWithJsonAttr(InlineElement):
    # parse common mark image + json attrs
    # ex. ![alt](url "title"){"a": "b"}
    pattern = re.compile(r'!\[(.+)\]\((\S+)(?:\s+"(.+)")?\)(\{.+\})')
    priority = 6
    # parse alt
    parse_children = True
    parse_group = 1

    def __init__(self, match):
        self.dest = match.group(2)
        self.title = match.group(3)
        raw_attrs = match.group(4)
        try:
            self.attrs = json.loads(raw_attrs)
        except:  # noqa: E722
            self.attrs = {}


class CustomImageRendererMixin:
    # override render_image to render figure with caption when title is provided
    def render_image(self, element):
        alt = self.render_children(element)
        src = element.dest
        title = element.title
        img_html = f'<img src="{src}" alt="{alt}">'
        if title:
            return f"<figure>{img_html}<figcaption>{title}</figcaption></figure>"
        return img_html

    # render function for ImageWithJsonAttr
    def render_image_with_json_attr(self, element):
        return self.render_image(element)


def process_posts(ctx):
    mk_ext = MarkoExtension(
        elements=[ImageWithJsonAttr], renderer_mixins=[CustomImageRendererMixin]
    )
    md = Markdown(extensions=[mk_ext])
    post_tpl = jj2_env.get_template("post.html")
    for file in posts_dir.iterdir():
        stat = file.stat()
        post = frontmatter.load(file)

        if post.get("draft"):
            continue

        slug = post.get("slug")
        if slug is None:
            slug = file.stem
            post["slug"] = slug

        if slug in ctx.get("posts_map"):
            raise PostSlugDuplication

        order = None
        split = slug.split("-")
        if len(split) > 0 and split[0].isdigit():
            order = int(split[0])
        post["order"] = order

        ast = md.parse(post.content)
        walk_ast_ctx = {
            "page_url": f"/posts/{slug}",
            "images": [],
            "text_blocks": [],
        }
        walk_ast(walk_ast_ctx, ast)

        ctx.get("images").extend(walk_ast_ctx.get("images"))

        html = md.convert(post.content)

        abstract = post.get("abstract")
        if abstract is None:
            abstract = " ".join(walk_ast_ctx.get("text_blocks"))
        post["abstract"] = abstract

        date = post.get("date")
        if date is None:
            created_ts = getattr(stat, "st_birthtime", stat.st_ctime)
            date = datetime.fromtimestamp(created_ts)
            post["date"] = date
        post["date_fmt"] = date.strftime("%b %d, %Y")

        dist_post_dir = dist_posts_dir.joinpath(slug)
        build_page(
            dist_post_dir.joinpath("index.html"),
            template=post_tpl,
            context={
                **base_render_ctx,
                **post,
                "post_html": html,
                "page_title": post.get("title"),
            },
        )

        ctx.get("posts").append(post)
        ctx.get("posts_map")[slug] = post


def build(args):
    process_posts_ctx = {"posts": [], "posts_map": {}, "images": []}
    process_posts(process_posts_ctx)

    sorted_posts = sorted(
        process_posts_ctx.get("posts"),
        key=lambda p: (-p.get("order"), -p.get("date").toordinal()),
    )

    build_page(
        dist_posts_dir.joinpath("index.html"),
        template_path="posts.html",
        context={**base_render_ctx, "posts": sorted_posts},
    )

    featured_posts = [
        process_posts_ctx.get("posts_map").get(slug)
        for slug in featured_post_slugs
        if slug in process_posts_ctx.get("posts_map")
    ]

    build_page(
        dist_dir.joinpath("index.html"),
        template_path="index.html",
        context={
            **base_render_ctx,
            "bmc_link": bmc_link,
            "working_email": working_email,
            "featured_posts": featured_posts,
            "platforms": platforms,
        },
    )

    build_page(
        dist_dir.joinpath("404.html"),
        template_path="404.html",
    )

    with ensure_dir_and_open_file(dist_assets_data_dir.joinpath("images.json")) as file:
        file.write(json.dumps(process_posts_ctx.get("images")))

    sass.compile(dirname=(assets_css_dir, dist_assets_css_dir))
    shutil.copytree(assets_images_dir, dist_assets_images_dir, dirs_exist_ok=True)
    shutil.copytree(assets_js_dir, dist_assets_js_dir, dirs_exist_ok=True)


def deploy(args):
    if not dist_dir.is_dir():
        logger.error("dist directory does not exist, run build first.")
        return
    if shutil.which("wrangler") is not None:
        logger.info("wrangler found, using it.")
        try:
            cmd = [
                "wrangler",
                "pages",
                "deploy",
                dist_dir,
                f"--project-name={cf_page_proj}",
                "--commit-dirty=true",
            ]
            result = subprocess.run(cmd, check=True)
            logger.info(
                "wrangler deploy complete with returncode {}.", result.returncode
            )
            return result.returncode
        except subprocess.CalledProcessError as e:
            return e.returncode
    else:
        logger.info("wrangler not found, falling back to cloudflare SDK deploy.")
        # TODO: implement this


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command")
    build_parser = subparsers.add_parser("build")
    build_parser.set_defaults(func=build)

    deploy_parser = subparsers.add_parser("deploy")
    deploy_parser.set_defaults(func=deploy)

    args = parser.parse_args()
    args.func(args)
